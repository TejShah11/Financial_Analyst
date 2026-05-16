from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite")

messages = [
    SystemMessage(content="You are a financial analyst."),
    HumanMessage(content="What is the standard formula for operating margin?"),
]

response = llm.invoke(messages)
print(response.content)
