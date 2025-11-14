from langchain_core.embeddings import Embeddings
from openai import OpenAI, AsyncOpenAI, NotGiven, NOT_GIVEN


class DoubaoTextEmbeddings(Embeddings):
    def __init__(self, model, api_key, base_url, dims: int | NotGiven = NOT_GIVEN):
        self.model = model
        self.dims = dims
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents using the OpenAI API.

        Args:
            texts: The list of texts to embed.

        Returns:
            A list of embeddings, one for each text.
        """
        resp = self.client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float",
            dimensions=self.dims
        )
        if not isinstance(resp, dict):
            resp = resp.model_dump()
        return [r["embedding"] for r in resp["data"]]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = await self.async_client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float",
            dimensions=self.dims
        )
        if not isinstance(resp, dict):
            resp = resp.model_dump()
        return [r["embedding"] for r in resp["data"]]

    async def aembed_query(self, text: str) -> list[float]:
        embeddings = await self.aembed_documents([text])
        return embeddings[0]
