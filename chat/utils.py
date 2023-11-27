import openai
import re
from django.conf import settings
from train.constants import OpenAIConstants
from openai.types.beta import Thread, Assistant
from openai.types.beta.threads import ThreadMessage

class OpenAIUtils:
    _client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    @classmethod
    def create_thread(cls) -> Thread:
        return cls._client.beta.threads.create()
    
    @classmethod
    def get_assistant_response(cls, assistant:Assistant, thread:Thread) -> str:
        '''
        run the thread and return the assistant's response
        '''
        run = cls._client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id
        )
        run_id = run.id

        # polling until its ready, this will get updated soon
        # ref: https://platform.openai.com/docs/assistants/how-it-works/limitations
        while run.status != "completed":
            run = cls._client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run_id
            )

        messages = cls._client.beta.threads.messages.list(thread.id)
        #print(f"DEBUG: found messages: {messages}")
        message = messages.data[0]
        text = message.content[0].text.value
        
        return text
    
    @classmethod
    def add_user_response(cls, thread:Thread, text:str) -> ThreadMessage:
        user_message = cls._client.beta.threads.messages.create(
            thread.id,
            role=OpenAIConstants.ROLES.USER,
            content=text,
        )

        return user_message
    