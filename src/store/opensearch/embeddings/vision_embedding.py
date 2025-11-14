from langchain_core.embeddings import Embeddings
from volcenginesdkarkruntime import Ark, AsyncArk
from volcenginesdkarkruntime.types.multimodal_embedding import MultimodalEmbeddingContentPartTextParam


class DoubaoVisionEmbeddings(Embeddings):
    def __init__(self, model, api_key, **kwargs):
        self.model = model
        self.client = Ark(api_key=api_key)
        self.async_client = AsyncArk(api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents using the OpenAI API.

        Args:
            texts: The list of texts to embed.

        Returns:
            A list of embeddings, one for each text.
        """
        # results = []
        # for text in texts:
        #     results.append(self.embed_query(text))
        # return results
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        resp = self.client.multimodal_embeddings.create(
            model=self.model,
            input=[
                MultimodalEmbeddingContentPartTextParam(type="text", text=text),
            ]
        )
        return resp.data["embedding"]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await self.aembed_query(text) for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        resp = await self.async_client.multimodal_embeddings.create(
            model=self.model,
            input=[
                MultimodalEmbeddingContentPartTextParam(type="text", text=text),
            ]
        )
        return resp.data["embedding"]
