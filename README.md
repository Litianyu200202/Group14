# Group14
prompt_real是要apikey的，mock是模拟ai回答，可以先测试模拟运行。
fastapi对接顺利，需要付费账户的apikey

新上传的tenantchatbot_sprint2_LLM是根据老师langchain的代码改的，思路应该更全。
contract_rag_noapi_demo不需要apikey，但基本没用，可以先忽略。

使用方式：
确保您安装了requirement.txt中的所有的包,请自备带有openai api的.env文件
在命令行中输入cd /Users/....../Group14（这取决于您的电脑路径）
uvicorn backend.api:app --reload
在另一个命令行中输入 streamlit run steeamlit_UI.py即可使用我们的tenant chatbot
