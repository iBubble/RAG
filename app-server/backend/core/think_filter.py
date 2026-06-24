"""
<think> 标签流式拦截器。
WHY: qwen3.6 模型会在输出中夹带 <think>...</think> 思考链，
     这些内容对终端用户无价值且会破坏 A4 画布的纯净度。
     我们需要在 SSE 流式输出的每个 chunk 上实时拦截，而非全量缓存后再过滤。
策略: 基于有限状态机逐字符扫描，处理跨 chunk 边界的标签碎片。
"""
from __future__ import annotations

import re
from enum import Enum, auto
from typing import AsyncGenerator


class _State(Enum):
    NORMAL = auto()      # 正常输出
    IN_THINK = auto()    # 在 <think> 块内，静默
    MAYBE_OPEN = auto()  # 可能遇到了 <think> 开头
    MAYBE_CLOSE = auto() # 可能遇到了 </think> 开头


class ThinkFilter:
    """流式 <think> 标签拦截状态机。"""

    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"

    def __init__(self):
        self._state = _State.NORMAL
        self._buffer = ""  # 暂存可能的标签碎片

    def feed(self, chunk: str) -> str:
        """
        喂入一个文本 chunk，返回过滤后应该输出的文本。
        在 <think>...</think> 内部的内容会被静默吞掉。
        """
        output = []
        i = 0
        text = self._buffer + chunk
        self._buffer = ""

        while i < len(text):
            char = text[i]

            if self._state == _State.NORMAL:
                # 检测是否遇到 < 开头（可能是 <think>）
                if char == "<":
                    remaining = text[i:]
                    if remaining.startswith(self.OPEN_TAG):
                        self._state = _State.IN_THINK
                        i += len(self.OPEN_TAG)
                        continue
                    elif len(remaining) < len(self.OPEN_TAG) and self.OPEN_TAG.startswith(remaining):
                        # 碎片：chunk 以 "<thi" 结尾，可能下个 chunk 才完整
                        self._buffer = remaining
                        return "".join(output)
                    else:
                        output.append(char)
                        i += 1
                else:
                    output.append(char)
                    i += 1

            elif self._state == _State.IN_THINK:
                # 在 think 块内，寻找 </think> 关闭标签
                if char == "<":
                    remaining = text[i:]
                    if remaining.startswith(self.CLOSE_TAG):
                        self._state = _State.NORMAL
                        i += len(self.CLOSE_TAG)
                        continue
                    elif len(remaining) < len(self.CLOSE_TAG) and self.CLOSE_TAG.startswith(remaining):
                        # 碎片
                        self._buffer = remaining
                        return "".join(output)
                    else:
                        i += 1  # 静默跳过
                else:
                    i += 1  # 静默跳过

        return "".join(output)

    def reset(self):
        """重置状态机。"""
        self._state = _State.NORMAL
        self._buffer = ""


async def filter_think_stream(
    stream: AsyncGenerator[str, None]
) -> AsyncGenerator[str, None]:
    """
    包装一个异步文本流，过滤掉其中的 <think>...</think> 块。
    并在开始和结束时发送特殊标记，供前端感知推理状态。
    """
    filt = ThinkFilter()
    # WHY: 旧版使用 emitted_start / emitted_end 一次性布尔锁，
    #       只能处理单个 <think> 块。当 LLM 输出多段推演时，
    #       第二个及后续的 <think> 块无法下发 THINK_START/END 标记，
    #       导致前端解析异常。改用 in_think 动态跟踪，支持无限次状态翻转。
    in_think = False

    async for chunk in stream:
        filtered = filt.feed(chunk)

        # 当状态进入 IN_THINK 且之前不在 think 中时，下发开始标记
        if filt._state == _State.IN_THINK and not in_think:
            yield "<<<THINK_START>>>"
            in_think = True

        # 当状态从 IN_THINK 恢复到 NORMAL 时，下发结束标记并重置
        if filt._state == _State.NORMAL and in_think:
            yield "<<<THINK_END>>>"
            in_think = False

        if filtered:
            yield filtered

async def format_think_stream(
    stream: AsyncGenerator[str, None]
) -> AsyncGenerator[str, None]:
    """
    流式格式化 <think> 标签，将其转化为 Markdown blockquote（引用语法）。
    这样前端即使用普通 Markdown 展示，也能看到“思考过程”被折叠在引用层中。
    """
    buffer = ""
    OPEN_TAG = "<think>"
    CLOSE_TAG = "</think>"
    in_think = False
    
    async for chunk in stream:
        buffer += chunk
        output = ""
        
        while buffer:
            if not in_think:
                # 寻找 <think>
                idx = buffer.find(OPEN_TAG)
                if idx != -1:
                    output += buffer[:idx]
                    output += "\n\n> 💭 **AI 深度推演中**...\n> \n> "
                    buffer = buffer[idx + len(OPEN_TAG):]
                    in_think = True
                else:
                    # 如果 buffer 结尾可能是 <think> 的前缀，则保留一点
                    possible_open = False
                    for i in range(1, len(OPEN_TAG)):
                        if buffer.endswith(OPEN_TAG[:i]):
                            output += buffer[:-i]
                            buffer = buffer[-i:]
                            possible_open = True
                            break
                    if not possible_open:
                        output += buffer
                        buffer = ""
                    else:
                        break  # WHY: 必须退出 while 循环，等待下一个 chunk 拼接到 buffer
                        
            else:
                # 寻找 </think>
                idx = buffer.find(CLOSE_TAG)
                if idx != -1:
                    think_content = buffer[:idx]
                    # 将内部的换行符替换为带 > 的换行
                    output += think_content.replace("\n", "\n> ")
                    output += "\n> \n> _（推演完毕）_\n\n---\n\n"
                    buffer = buffer[idx + len(CLOSE_TAG):]
                    in_think = False
                else:
                    possible_close = False
                    for i in range(1, len(CLOSE_TAG)):
                        if buffer.endswith(CLOSE_TAG[:i]):
                            think_content = buffer[:-i]
                            output += think_content.replace("\n", "\n> ")
                            buffer = buffer[-i:]
                            possible_close = True
                            break
                    if not possible_close:
                        output += buffer.replace("\n", "\n> ")
                        buffer = ""
                    else:
                        break  # WHY: 等待下一个 chunk 拼接
                        
        if output:
            yield output

    # 结束前如果还有遗留内容（例如未闭合的 buffer）
    if buffer:
        if in_think:
            yield buffer.replace("\n", "\n> ")
        else:
            yield buffer
