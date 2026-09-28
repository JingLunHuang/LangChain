from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_community.chat_models import ChatTongyi
import json
import os
import dashscope

# 从环境变量获取 dashscope 的 API Key
api_key = os.environ.get('DASHSCOPE_API_KEY')
dashscope.api_key = api_key

# 自定义工具1：文本分析工具
@tool
def text_analysis(text: str) -> str:
    """分析文本内容，提取字数、字符数和情感倾向
    
    参数:
        text: 要分析的文本
    返回:
        分析结果
    """
    # 简单的文本分析示例
    word_count = len(text.split())
    char_count = len(text)
    
    # 简单的情感分析（示例）
    positive_words = ["好", "优秀", "喜欢", "快乐", "成功", "美好"]
    negative_words = ["差", "糟糕", "讨厌", "悲伤", "失败", "痛苦"]
    
    positive_count = sum(1 for word in positive_words if word in text)
    negative_count = sum(1 for word in negative_words if word in text)
    
    sentiment = "积极" if positive_count > negative_count else "消极" if negative_count > positive_count else "中性"
    
    return f"文本分析结果:\n- 字数: {word_count}\n- 字符数: {char_count}\n- 情感倾向: {sentiment}"

# 自定义工具2：数据转换工具
@tool
def data_conversion(input_data: str, input_format: str, output_format: str) -> str:
    """在不同数据格式之间转换，如JSON、CSV等
    
    参数:
        input_data: 输入数据
        input_format: 输入格式
        output_format: 输出格式
    返回:
        转换后的数据
    """
    try:
        if input_format.lower() == "json" and output_format.lower() == "csv":
            # JSON到CSV的转换示例
            data = json.loads(input_data)
            if isinstance(data, list):
                if not data:
                    return "空数据"
                
                # 获取所有可能的列
                headers = set()
                for item in data:
                    headers.update(item.keys())
                headers = list(headers)
                
                # 创建CSV
                csv = ",".join(headers) + "\n"
                for item in data:
                    row = [str(item.get(header, "")) for header in headers]
                    csv += ",".join(row) + "\n"
                
                return csv
            else:
                return "输入数据必须是JSON数组"
        
        elif input_format.lower() == "csv" and output_format.lower() == "json":
            # CSV到JSON的转换示例
            lines = input_data.strip().split("\n")
            if len(lines) < 2:
                return "CSV数据至少需要标题行和数据行"
            
            headers = lines[0].split(",")
            result = []
            
            for line in lines[1:]:
                values = line.split(",")
                if len(values) != len(headers):
                    continue
                
                item = {}
                for i, header in enumerate(headers):
                    item[header] = values[i]
                result.append(item)
            
            return json.dumps(result, ensure_ascii=False, indent=2)
        
        else:
            return f"不支持的转换: {input_format} -> {output_format}"
    
    except Exception as e:
        return f"转换失败: {str(e)}"

# 自定义工具3：文本处理工具 - 统计行数
@tool
def count_lines(content: str) -> str:
    """统计文本内容的行数
    
    参数:
        content: 文本内容
    返回:
        行数统计结果
    """
    return f"文本共有 {len(content.splitlines())} 行"

# 自定义工具4：文本处理工具 - 查找文本
@tool
def find_text(content: str, search_text: str) -> str:
    """在文本内容中查找指定文本
    
    参数:
        content: 文本内容
        search_text: 要查找的文本
    返回:
        查找结果
    """
    if not search_text:
        return "请提供要查找的文本"
    
    lines = content.splitlines()
    matches = []
    
    for i, line in enumerate(lines):
        if search_text in line:
            matches.append(f"第 {i+1} 行: {line}")
    
    if matches:
        return f"找到 {len(matches)} 处匹配:\n" + "\n".join(matches)
    else:
        return f"未找到文本 '{search_text}'"

# 自定义工具5：文本处理工具 - 替换文本
@tool
def replace_text(content: str, old_text: str, new_text: str) -> str:
    """在文本内容中替换指定文本
    
    参数:
        content: 文本内容
        old_text: 要替换的旧文本
        new_text: 替换后的新文本
    返回:
        替换结果
    """
    if not old_text:
        return "请提供要替换的文本"
    
    new_content = content.replace(old_text, new_text)
    count = content.count(old_text)
    
    return f"替换完成，共替换 {count} 处。\n新内容:\n{new_content}"

# 创建工具链
def create_tool_chain():
    """创建工具链"""
    # 组合工具
    tools = [
        text_analysis,
        data_conversion,
        count_lines,
        find_text,
        replace_text
    ]
    
    # 初始化语言模型（使用 ChatModel 以支持 tool calling）
    llm = ChatTongyi(model_name="qwen-turbo", dashscope_api_key=api_key)
    
    # 创建Agent（LangChain 1.x 新写法）
    agent = create_agent(llm, tools)
    
    return agent

# 示例：使用工具链处理任务
def process_task(task_description):
    """
    使用工具链处理任务
    
    参数:
        task_description: 任务描述
    返回:
        处理结果
    """
    try:
        agent = create_tool_chain()
        result = agent.invoke({"messages": [("user", task_description)]})
        return result["messages"][-1].content  # 从返回的字典中提取输出
    except Exception as e:
        return f"处理任务时出错: {str(e)}"

# 示例用法
if __name__ == "__main__":
    # 示例1: 文本分析与处理
    task1 = "分析以下文本的情感倾向，并统计其中的行数：'这个产品非常好用，我很喜欢它的设计，使用体验非常棒！\n价格也很合理，推荐大家购买。\n客服态度也很好，解答问题很及时。'"
    print("任务1:", task1)
    print("结果:", process_task(task1))
    
    # 示例2: 数据格式转换
    task2 = "将以下CSV数据转换为JSON格式：'name,age,comment\n张三,25,这个产品很好\n李四,30,服务态度差\n王五,28,性价比高'"
    print("\n任务2:", task2)
    print("结果:", process_task(task2))