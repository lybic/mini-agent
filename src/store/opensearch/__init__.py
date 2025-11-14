from dateutil import parser
from typing import Iterable, cast, Optional, Sequence

from langchain_core.embeddings import Embeddings
from langgraph.store.base import BaseStore, Op, Result, GetOp, PutOp, SearchOp, IndexConfig, ensure_embeddings, \
    tokenize_path, get_text_at_path, ListNamespacesOp, SearchItem, Item
from opensearchpy import OpenSearch, SSLError
from opensearchpy.exceptions import NotFoundError

from .base import _group_ops, _namespace_to_text


class OpenSearchStore(BaseStore):
    def __init__(
            self,
            https_client: OpenSearch,
            http_client: OpenSearch,
            *,
            index: Optional[IndexConfig] = None,
            store_prefix: str = "store",
            threshold: float = 0.8
    ) -> None:
        BaseStore.__init__(self)
        self.https_client = https_client
        self.http_client = http_client
        self.index_config = index
        self.threshold = threshold

        self.index_config = index
        if self.index_config:
            self.index_config = self.index_config.copy()
            self.embeddings: Optional[Embeddings] = ensure_embeddings(
                self.index_config.get("embed"),
            )
            self.index_config["__tokenized_fields"] = [
                (p, tokenize_path(p)) if p != "$" else (p, p)
                for p in (self.index_config.get("fields") or ["$"])
            ]
        else:
            self.index_config = None
            self.embeddings = None

        self.data_index = f"{store_prefix}_data"
        client = self.get_client()
        if not client.indices.exists_template(name=self.data_index):
            # todo 不更新created_at
            client.ingest.put_pipeline(
                id="ingest_with_timestamps",
                body={
                    "processors": [
                        {
                            "set": {
                                "if": "ctx?.created_at == null",
                                "field": "created_at",
                                "value": "{{_ingest.timestamp}}"
                            }
                        },
                        {
                            "set": {
                                "field": "updated_at",
                                "value": "{{_ingest.timestamp}}"
                            }
                        }
                    ]
                }
            )
            body = {
                "index_patterns": [f"{self.data_index}_*"],
                "template": {
                    "settings": {
                        "default_pipeline": "ingest_with_timestamps"
                    },
                    "mappings": {
                        "properties": {
                            "data": {
                                "type": "object"
                            },
                            "created_at": {
                                "type": "date",
                            },
                            "updated_at": {
                                "type": "date"
                            },
                        }
                    }
                }
            }
            client.indices.put_index_template(name=self.data_index, body=body)

        if self.index_config:
            dims = self.index_config["dims"]
            self.vector_index = f"{store_prefix}_vector_{dims}"

            if not client.indices.exists_template(name=self.vector_index):
                body = {
                    "index_patterns": [f"{self.vector_index}_*"],
                    "template": {
                        "settings": {
                            "index": {
                                "knn": True,
                                "knn.space_type": "cosinesimil",
                            }
                        },
                        "mappings": {
                            "properties": {
                                "embedding": {
                                    "type": "knn_vector",
                                    "dimension": dims,
                                    "method": {
                                        "name": "hnsw",
                                        "engine": "nmslib",
                                        "space_type": "cosinesimil"
                                    }
                                },
                                "key": {
                                    "type": "keyword"
                                }
                            }
                        }
                    }
                }
                client.indices.put_index_template(name=self.vector_index, body=body)

    def get_client(self) -> OpenSearch:
        client = self.https_client
        try:
            client.info()
        except SSLError:
            client = self.http_client
        return client

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        pass

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        grouped_ops, num_ops = _group_ops(ops)
        results: list[Result] = [None] * num_ops

        if GetOp in grouped_ops:
            self._batch_get_ops(
                cast(list[tuple[int, GetOp]], grouped_ops[GetOp]), results
            )

        if PutOp in grouped_ops:
            self._batch_put_ops(cast(list[tuple[int, PutOp]], grouped_ops[PutOp]))

        if SearchOp in grouped_ops:
            self._batch_search_ops(
                cast(list[tuple[int, SearchOp]], grouped_ops[SearchOp]), results
            )

        if ListNamespacesOp in grouped_ops:
            self._batch_list_namespaces_ops(
                cast(
                    Sequence[tuple[int, ListNamespacesOp]],
                    grouped_ops[ListNamespacesOp],
                ),
                results,
            )

        return results

    def _batch_get_ops(self, get_ops: list[tuple[int, GetOp]], results: list[Result]):
        client = self.get_client()
        for idx, get_op in get_ops:
            ns = _namespace_to_text(get_op.namespace)
            index_name = f"{self.data_index}_{ns}"
            doc = client.get(index=index_name, id=get_op.key)
            results[idx] = Item(namespace=get_op.namespace, key=get_op.key, value=doc["_source"]["data"],
                                created_at=parser.isoparse(doc["_source"]["created_at"]),
                                updated_at=parser.isoparse(doc["_source"]["updated_at"]))

    def _batch_put_ops(self, put_ops: list[tuple[int, PutOp]]):
        client = self.get_client()
        for idx, put_op in put_ops:
            ns = _namespace_to_text(put_op.namespace)
            data_index_name = f"{self.data_index}_{ns}"
            vector_index_name = f"{self.vector_index}_{ns}"

            if put_op.value is None:
                client.delete(index=data_index_name, id=put_op.key)

                if self.index_config:
                    client.delete_by_query(index=vector_index_name, body={
                        "query": {
                            "term": {
                                "key": put_op.key
                            }
                        }
                    })

                continue

            client.index(index=data_index_name, id=put_op.key, body={"data": put_op.value})

            if self.index_config and put_op.index is not False:
                to_embed: list[tuple[str, str]] = []
                paths = (
                    self.index_config["__tokenized_fields"]
                    if put_op.index is None
                    else [(ix, tokenize_path(ix)) for ix in put_op.index]
                )
                for path, field in paths:
                    texts = get_text_at_path(put_op.value, field)
                    if not texts:
                        continue
                    if len(texts) > 1:
                        for i, text in enumerate(texts):
                            to_embed.append(
                                (f"{path}.{i}", text)
                            )
                    else:
                        to_embed.append((path, texts[0]))

                if not to_embed:
                    continue

                vectors = self.embeddings.embed_documents(
                    [text for _, text in to_embed]
                )

                for (path, _), vector in zip(to_embed, vectors):
                    client.index(index=vector_index_name, id=f"{put_op.key}_{path}", body={
                        "key": put_op.key,
                        "field_name": path,
                        "embedding": (
                            vector.tolist() if hasattr(vector, "tolist") else vector
                        )
                    })

    def _batch_search_ops(self, search_ops: list[tuple[int, SearchOp]], results: list[Result]):
        if not self.index_config or not self.embeddings or not search_ops:
            return

        client = self.get_client()
        for idx, search_op in search_ops:
            ns = _namespace_to_text(search_op.namespace_prefix)
            data_index_name = f"{self.data_index}_{ns}"
            vector_index_name = f"{self.vector_index}_{ns}"

            vector = self.embeddings.embed_query(search_op.query)
            limit = search_op.limit if search_op.limit is not None else 3
            body = {
                "size": limit,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": vector,
                            "k": limit,
                        }
                    }
                },
                "_source": ["key"]
            }
            try:
                vector_results = client.search(index=vector_index_name, body=body)
            except NotFoundError:
                continue

            items = []
            for hit in vector_results["hits"]["hits"]:
                score = hit["_score"]
                if score < self.threshold:
                    continue
                key = hit["_source"]["key"]
                doc = client.get(index=data_index_name, id=key)
                items.append(SearchItem(
                    namespace=search_op.namespace_prefix,
                    key=key,
                    value=doc["_source"]["data"],
                    created_at=parser.isoparse(doc["_source"]["created_at"]),
                    updated_at=parser.isoparse(doc["_source"]["updated_at"]),
                    score=score,
                ))
            results[idx] = items

    def _batch_list_namespaces_ops(self, param, results):
        pass
