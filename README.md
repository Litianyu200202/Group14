# Group14
prompt_real是要apikey的，mock是模拟ai回答，可以先测试模拟运行。
fastapi对接顺利，需要付费账户的apikey

新上传的tenantchatbot_sprint2_LLM是根据老师langchain的代码改的，思路应该更全。
contract_rag_noapi_demo不需要apikey，但基本没用，可以先忽略。

使用方式：
在命令行中输入cd /Users/....../Group14
uvicorn backend:api:app --reload
另开一个命令行，使用curl测试
curl http://127.0.0.1:8000/ping

curl -X POST "http://127.0.0.1:8000/chat" \
     -H "Content-Type: application/json" \
     -d '{"user_id": "U001", "message": "Who is responsible for aircon maintenance?"}'

curl -X POST "http://127.0.0.1:8000/chat" \
     -H "Content-Type: application/json" \
     -d '{"user_id": "U001", "message": "Can I terminate the lease early?"}'

curl -X POST "http://127.0.0.1:8000/chat" \
     -H "Content-Type: application/json" \
     -d '{"user_id": "U001", "message": "I want to know the deposit refund clause."}'
