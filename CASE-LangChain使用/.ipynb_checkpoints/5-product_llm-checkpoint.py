import os
import textwrap
import time

from langchain_community.chat_models import ChatTongyi
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
from langchain.agents import create_agent

# 定义了LLM的Prompt Template
CONTEXT_QA_TMPL = """
根据以下提供的信息，回答用户的问题
信息：{context}

问题：{query}
"""
CONTEXT_QA_PROMPT = PromptTemplate(
    input_variables=["query", "context"],
    template=CONTEXT_QA_TMPL,
)

# 输出结果显示，每行最多60字符，每个字符显示停留0.1秒（动态显示效果）
def output_response(response: str) -> None:
    if not response:
        exit(0)
    for line in textwrap.wrap(response, width=60):
        for word in line.split():
            for char in word:
                print(char, end="", flush=True)
                time.sleep(0.1)
            print(" ", end="", flush=True)
        print()
    print("----------------------------------------------------------------")

# 从环境变量获取 API Key
api_key = os.getenv('DASHSCOPE_API_KEY')

# 定义LLM
llm = ChatTongyi(model_name="qwen-turbo", dashscope_api_key=api_key)

# 工具1：产品描述
@tool
def find_product_description(product_name: str) -> str:
    """通过产品名称找到产品描述。输入产品名称如 Model 3, Model Y, Model X"""
    print('product_name=', product_name)
    product_info = {
        "Model 3": "具有简洁、动感的外观设计，流线型车身和现代化前脸。定价23.19-33.19万",
        "Model Y": "在外观上与Model 3相似，但采用了更高的车身和更大的后备箱空间。定价26.39-36.39万",
        "Model X": "拥有独特的翅子门设计和更加大胆的外观风格。定价89.89-105.89万",
    }
    return product_info.get(product_name, "没有找到这个产品")

# 工具2：公司介绍
@tool
def find_company_info(query: str) -> str:
    """当用户询问公司相关的问题时使用。输入用户的问题"""
    context = """
    特斯拉最知名的产品是电动汽车，其中包括Model S、Model 3、Model X和Model Y等多款车型。
    特斯拉以其技术创新、高性能和领先的自动驾驶技术而闻名。公司不断推动自动驾驶技术的研发，并在车辆中引入了各种驾驶辅助功能，如自动紧急制动、自适应巡航控制和车道保持辅助等。
    """
    prompt = CONTEXT_QA_PROMPT.format(query=query, context=context)
    response = llm.invoke(prompt)
    return response.content

# 定义工具集
tools = [find_product_description, find_company_info]

# 创建 Agent
agent = create_agent(llm, tools)

if __name__ == "__main__":
    # 主过程：可以一直提问下去，直到Ctrl+C
    while True:
        user_input = input("请输入您的问题：")
        result = agent.invoke({"messages": [("user", user_input)]})
        response = result["messages"][-1].content
        output_response(response)
