# 第三方组件与模型

卡输咪应用源码由川宁（Create4220）以 MIT 许可发布；以下组件不因随安装包分发而改用本项目的 MIT 许可。安装包保留各组件的原始许可和模型名称。

| 组件 | 来源 / 作者 | 许可文件 |
| --- | --- | --- |
| SenseVoiceSmall INT8 ONNX，sense-voice-zh-en-ja-ko-yue-2024-07-17 | 阿里巴巴通义语音团队 / FunAudioLLM；ONNX 导出由 sherpa-onnx 项目提供 | licenses/FunASR-MODEL-LICENSE.txt；models/sensevoice/LICENSE |
| sherpa-onnx 2.0.1 | k2-fsa/sherpa-onnx | licenses/sherpa-onnx-LICENSE.txt |
| ONNX Runtime 1.28.2 | Microsoft | licenses/ONNX-Runtime-LICENSE.txt |
| NumPy 2.3.5 及其二进制依赖 | NumPy 与对应上游作者 | licenses/NumPy-LICENSE.txt |
| Python 3.12 及标准运行组件 | Python Software Foundation 与对应上游作者 | licenses/Python-LICENSE.txt |

SenseVoice 模型采用 FunASR 模型开源协议；协议允许按条款使用、复制和分享，并要求保留来源、作者与模型名称。请阅读随包完整协议及其限制。

上游来源：
- https://github.com/FunAudioLLM/SenseVoice
- https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE
- https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17
- https://github.com/k2-fsa/sherpa-onnx
- https://github.com/microsoft/onnxruntime
- https://numpy.org/
- https://www.python.org/

中文安装向导使用 Inno Setup 官方中文翻译文件，维护者署名保留在该文件中。Inno Setup 仅作为构建工具，编译器不随应用运行。
