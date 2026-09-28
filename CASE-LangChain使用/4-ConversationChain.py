import os
from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
import dashscope

# 从环境变量获取 dashscope 的 API Key
api_key = os.getenv('DASHSCOPE_API_KEY')
dashscope.api_key = api_key

# 加载模型
llm = ChatTongyi(model_name="qwen-turbo", dashscope_api_key=api_key)

# 创建带历史记录的 prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{input}")
])

# 创建 chain
chain = prompt | llm

# 存储会话历史
store = {}

def get_session_history(session_id: str):
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]

# 创建带记忆的对话链
conversation = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history"
)

config = {"configurable": {"session_id": "default"}}

# 第一轮对话
output = conversation.invoke({"input": "Hi there!"}, config=config)
print(output.content)

# 第二轮对话 (会记住上一轮)
output = conversation.invoke({"input": "I'm doing well! Just having a conversation with an AI."}, config=config)
print(output.content)
