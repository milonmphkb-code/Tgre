import asyncio
from sqlalchemy import select, desc
from app.db import GroupSetting, GroupMessage

class AIEngine:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self._gemini_client = None

    async def _gemini_answer(self, system: str, messages: list[dict]) -> str:
        from google import genai

        if self._gemini_client is None:
            self._gemini_client = genai.Client(api_key=self.settings.ai_api_key)

        parts = [system]
        for m in messages:
            role = m["role"].upper()
            parts.append(f"{role}: {m['content']}")
        prompt = "\n\n".join(parts)

        response = await asyncio.to_thread(
            self._gemini_client.models.generate_content,
            model=self.settings.ai_model,
            contents=prompt,
        )
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini returned an empty response")
        return text.strip()

    async def _openai_compatible_answer(self, system: str, messages: list[dict]) -> str:
        import httpx
        headers = {
            "Authorization": f"Bearer {self.settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.ai_model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0.4,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(self.settings.ai_api_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    async def answer(self, chat_id: int, user_text: str) -> str:
        async with self.db.session() as session:
            gs = (await session.execute(
                select(GroupSetting).where(GroupSetting.chat_id == chat_id)
            )).scalar_one_or_none()
            if not gs or not gs.enabled:
                return ""

            context = []
            if gs.context_enabled:
                rows = (await session.execute(
                    select(GroupMessage)
                    .where(GroupMessage.chat_id == chat_id)
                    .order_by(desc(GroupMessage.id))
                    .limit(min(gs.context_limit, self.settings.max_context_messages))
                )).scalars().all()
                context = [{"role": "user", "content": x.text} for x in reversed(rows)]

            system = (
                f"{gs.prompt}\n"
                f"Style: {gs.style}.\n"
                f"Answer length: {gs.length}.\n"
                "Automatically detect the user's language and answer in the same language. "
                "Be helpful, polite and concise. Do not claim to be human."
            )

        if not self.settings.ai_api_key:
            return "AI API configuration is incomplete."

        messages = [*context, {"role": "user", "content": user_text}]

        if self.settings.ai_provider == "gemini":
            return await self._gemini_answer(system, messages)
        return await self._openai_compatible_answer(system, messages)
