# 2-simple_toolchain.py
# 使用 LCEL（LangChain Expression Language）方式构建多工具任务链

from langchain_core.runnables import RunnableLambda, RunnableMap, RunnablePassthrough
import json
import os
import dashscope

# 从环境变量获取 dashscope 的 API Key
api_key = os.environ.get('DASHSCOPE_API_KEY')
dashscope.api_key = api_key

# 自定义工具1：文本分析工具
class TextAnalysisTool:
    """文本分析工具，用于分析文本内容"""
    def __init__(self):
        self.name = "文本分析"
        self.description = "分析文本内容，提取字数、字符数和情感倾向"
    def run(self, text: str) -> str:
        word_count = len(text.split())
        char_count = len(text)
        positive_words = ["好", "优秀", "喜欢", "快乐", "成功", "美好"]
        negative_words = ["差", "糟糕", "讨厌", "悲伤", "失败", "痛苦"]
        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)
        sentiment = "积极" if positive_count > negative_count else "消极" if negative_count > positive_count else "中性"
        return f"文本分析结果:\n- 字数: {word_count}\n- 字符数: {char_count}\n- 情感倾向: {sentiment}"

# 自定义工具2：数据转换工具
class DataConversionTool:
    """数据转换工具，用于在不同格式之间转换数据"""
    def __init__(self):
        self.name = "数据转换"
        self.description = "在不同数据格式之间转换，如JSON、CSV等"
    def run(self, input_data: str, input_format: str, output_format: str) -> str:
        try:
            if input_format.lower() == "json" and output_format.lower() == "csv":
                data = json.loads(input_data)
                if isinstance(data, list):
                    if not data:
                        return "空数据"
                    headers = set()
                    for item in data:
                        headers.update(item.keys())
                    headers = list(headers)
                    csv = ",".join(headers) + "\n"
                    for item in data:
                        row = [str(item.get(header, "")) for header in headers]
                        csv += ",".join(row) + "\n"
                    return csv
                else:
                    return "输入数据必须是JSON数组"
            elif input_format.lower() == "csv" and output_format.lower() == "json":
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

# 自定义工具3：文本处理工具
class TextProcessingTool:
    """文本处理工具，用于处理文本内容"""
    def __init__(self):
        self.name = "文本处理"
        self.description = "处理文本内容，如查找、替换、统计等"
    def run(self, operation: str, content: str, **kwargs) -> str:
        if operation == "count_lines":
            return f"文本共有 {len(content.splitlines())} 行"
        elif operation == "find_text":
            search_text = kwargs.get("search_text", "")
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
        elif operation == "replace_text":
            old_text = kwargs.get("old_text", "")
            new_text = kwargs.get("new_text", "")
            if not old_text:
                return "请提供要替换的文本"
            new_content = content.replace(old_text, new_text)
            count = content.count(old_text)
            return f"替换完成，共替换 {count} 处。\n新内容:\n{new_content}"
        else:
            return f"不支持的操作: {operation}"

# 工具实例
text_analysis = TextAnalysisTool()
data_conversion = DataConversionTool()
text_processing = TextProcessingTool()

# 工具链（LCEL风格）- 使用 RunnableLambda 包装工具函数
text_analysis_chain = RunnableLambda(lambda x: text_analysis.run(x["text"]))
data_conversion_chain = RunnableLambda(lambda x: data_conversion.run(
    x["input_data"], 
    x["input_format"], 
    x["output_format"]
))
count_lines_chain = RunnableLambda(lambda x: text_processing.run("count_lines", x["content"]))
find_text_chain = RunnableLambda(lambda x: text_processing.run(
    "find_text", 
    x["content"], 
    search_text=x.get("search_text", "")
))
replace_text_chain = RunnableLambda(lambda x: text_processing.run(
    "replace_text", 
    x["content"], 
    old_text=x.get("old_text", ""),
    new_text=x.get("new_text", "")
))

# LCEL 工具字典（用于快速查找）
tools = {
    "文本分析": text_analysis_chain,
    "数据转换": data_conversion_chain,
    "统计行数": count_lines_chain,
    "查找文本": find_text_chain,
    "替换文本": replace_text_chain,
}

# 示例：LCEL任务链 - 单个工具调用
def lcel_task_chain(task_type, params):
    """
    LCEL风格的任务链调度
    参数:
        task_type: 工具名称
        params: 参数字典
    返回:
        工具执行结果
    """
    if task_type not in tools:
        return "不支持的工具类型"
    return tools[task_type].invoke(params)

# LCEL 链式组合示例：文本分析 -> 统计行数
def lcel_analysis_and_count_chain(text):
    """
    使用 LCEL 管道操作符组合多个工具
    先分析文本，再统计行数
    """
    # 使用 RunnablePassthrough 传递数据，然后组合多个工具
    chain = (
        RunnablePassthrough.assign(
            analysis=lambda x: text_analysis_chain.invoke({"text": x["text"]})
        )
        | RunnableLambda(lambda x: {
            "analysis": x["analysis"],
            "line_count": count_lines_chain.invoke({"content": x["text"]})
        })
    )
    return chain.invoke({"text": text})

# LCEL 并行执行示例：同时执行多个工具
def lcel_parallel_tools(text):
    """
    使用 RunnableMap 并行执行多个工具
    """
    parallel_chain = RunnableMap({
        "analysis": RunnableLambda(lambda x: text_analysis_chain.invoke({"text": x["text"]})),
        "line_count": RunnableLambda(lambda x: count_lines_chain.invoke({"content": x["text"]})),
    })
    return parallel_chain.invoke({"text": text})

# 示例用法
if __name__ == "__main__":
    # 示例1：文本分析（单个工具调用）
    result1 = lcel_task_chain("文本分析", {"text": "这个产品非常好用，我很喜欢它的设计，使用体验非常棒！"})
    print("示例1结果（文本分析）：", result1)
    print("-" * 30)

    # 示例2：数据格式转换（单个工具调用）
    csv_data = "name,age,comment\n张三,25,这个产品很好\n李四,30,服务态度差\n王五,28,性价比高"
    result2 = lcel_task_chain("数据转换", {"input_data": csv_data, "input_format": "csv", "output_format": "json"})
    print("示例2结果（数据转换）：", result2)
    print("-" * 30)

    # 示例3：统计行数（单个工具调用）
    text = "第一行内容\n第二行内容\n第三行内容"
    result3 = lcel_task_chain("统计行数", {"content": text})
    print("示例3结果（统计行数）：", result3)
    print("-" * 30)

    # 示例4：LCEL 链式组合（先文本分析，再统计行数）
    # 使用 LCEL 管道操作符组合多个工具
    text4 = "这个产品非常好用，我很喜欢它的设计，使用体验非常棒！\n价格也很合理，推荐大家购买。\n客服态度也很好，解答问题很及时。"
    result4 = lcel_analysis_and_count_chain(text4)
    print("示例4结果（LCEL链式组合）：")
    print("文本分析结果：", result4["analysis"])
    print("行数统计结果：", result4["line_count"])
    print("-" * 30)

    # 示例5：LCEL 并行执行（同时执行多个工具）
    # 使用 RunnableMap 并行执行多个工具
    text5 = "这个产品非常好用，我很喜欢它的设计，使用体验非常棒！\n价格也很合理，推荐大家购买。"
    result5 = lcel_parallel_tools(text5)
    print("示例5结果（LCEL并行执行）：")
    print("文本分析结果：", result5["analysis"])
    print("行数统计结果：", result5["line_count"])
    print("-" * 30)

    # 示例6：查找文本
    text6 = "第一行：这是测试文本\n第二行：包含关键词\n第三行：继续测试"
    result6 = lcel_task_chain("查找文本", {"content": text6, "search_text": "关键词"})
    print("示例6结果（查找文本）：", result6)
    print("-" * 30)

    # 示例7：替换文本
    text7 = "原始文本内容\n需要替换的部分\n继续内容"
    result7 = lcel_task_chain("替换文本", {"content": text7, "old_text": "需要替换的部分", "new_text": "已替换的内容"})
    print("示例7结果（替换文本）：", result7)
    print("-" * 30)