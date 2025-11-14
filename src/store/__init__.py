import os
import threading
from opensearchpy import OpenSearch, Urllib3HttpConnection
import socket
from urllib3.connection import HTTPConnection

from .opensearch import OpenSearchStore

HTTPConnection.default_socket_options = [
    (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
    (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
    (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 300),
    (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)
]

_os_https_client, _os_http_client = None, None
_opensearch_lock = threading.Lock()


def get_opensearch_client():
    global _os_https_client, _os_http_client, _opensearch_lock

    if _os_https_client is not None:
        return _os_https_client, _os_http_client

    opensearch_config = {
        "host": "",
        "port": 9200,
        "username": "admin",
        "password": "admin",
        "text_embedding":"doubao-embedding-text-240715",
        "text_embedding_dims":"",
    }
    if opensearch_config["host"] == "":
        return _os_https_client, _os_http_client

    with _opensearch_lock:
        if _os_https_client is None:
            _os_https_client = OpenSearch(
                hosts=[
                    {
                        "host": opensearch_config["host"],
                        "port": opensearch_config["port"],
                    }
                ],
                scheme="https",
                http_auth=(opensearch_config["username"], opensearch_config["password"]),
                use_ssl=True,
                verify_certs=False,
                ssl_assert_hostname=False,
                ssl_show_warn=False,
                connection_class=Urllib3HttpConnection
            )
            _os_http_client = OpenSearch(
                hosts=[
                    {
                        "host": opensearch_config["host"],
                        "port": opensearch_config["port"],
                    }
                ],
                scheme="http",
                http_auth=(opensearch_config["username"], opensearch_config["password"]),
                connection_class=Urllib3HttpConnection
            )

    return _os_https_client, _os_http_client


_opensearch_store = None
_opensearch_store_lock = threading.Lock()


def get_opensearch_store():
    global _opensearch_store, _opensearch_store_lock
    if _opensearch_store is not None:
        return _opensearch_store

    os_https_client, os_http_client = get_opensearch_client()
    if os_https_client is None:
        return _opensearch_store

    with _opensearch_store_lock:
        if _opensearch_store is None:
            from langgraph.store.base import IndexConfig
            from playground.store.opensearch.embeddings.vision_embedding import DoubaoVisionEmbeddings

            embeddings = DoubaoVisionEmbeddings("doubao-embedding-text-240715", os.environ.get('ARK_API_KEY'))
            index_config = IndexConfig(embed=embeddings, dims=2048)
            _opensearch_store = OpenSearchStore(os_https_client, os_http_client, index=index_config,
                                                threshold=0.6)
    return _opensearch_store
