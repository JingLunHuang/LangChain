import os
from langchain_community.agent_toolkits.load_tools import load_tools
from langchain_community.chat_models import ChatTongyi
from langchain.agents import create_agent
from langchain_core.tools import tool
import dashscope

# 从环境变量获取 dashscope 的 API Key
api_key = os.getenv('DASHSCOPE_API_KEY')
dashscope.api_key = api_key

# 加载模型 (使用 ChatModel 以支持 tool calling)
llm = ChatTongyi(model_name="deepseek-v3", dashscope_api_key=api_key)

# 自定义数学计算工具 (替代已废弃的 llm-math)
@tool
def calculator(expression: str) -> str:
    """计算数学表达式。只接受数字和运算符，例如: 2+2, 100/4, 32*1.8+32。不要使用变量名或占位符。"""
    # 只允许数字、运算符和括号
    import re
    if not re.match(r'^[\d\s\+\-\*\/\.\(\)]+$', expression):
        return f"错误: 表达式 '{expression}' 包含无效字符。请只使用数字和运算符(+,-,*,/)"
    return str(eval(expression))

# 加载 serpapi 工具 + 自定义计算器
serpapi_tools = load_tools(["serpapi"])
tools = serpapi_tools + [calculator]

# LangChain 1.x 新写法
agent = create_agent(llm, tools)

# 运行 agent
result = agent.invoke({"messages": [("user", "当前北京的温度是多少华氏度？这个温度的1/4是多少")]})
print(result["messages"][-1].content)
