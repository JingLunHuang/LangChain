import os
from langchain_community.agent_toolkits.load_tools import load_tools
from langchain_community.chat_models import ChatTongyi
from langchain.agents import create_agent
import dashscope

# 从环境变量获取 dashscope 的 API Key
api_key = os.getenv('DASHSCOPE_API_KEY')
dashscope.api_key = api_key

# 加载模型 (使用 ChatModel 以支持 tool calling)
llm = ChatTongyi(model_name="qwen-turbo", dashscope_api_key=api_key)

# 加载 serpapi 工具
tools = load_tools(["serpapi"])

# LangChain 1.x 新写法
agent = create_agent(llm, tools)

# 运行 agent
result = agent.invoke({"messages": [("user", "今天是几月几号?历史上的今天有哪些名人出生")]})
print(result["messages"][-1].content)
