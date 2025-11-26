import ollama
import json

# Low-latency LLM call
def call_llm(messages):
    response = ollama.chat(
        model="phi3:mini",
    )
    return response["message"]["content"]

# Decides what the assistant should do next

def planner_agent(user_msg,state):
    system = """
    You are PlannerAgent.
    You decide the NEXT ACTION in the conversation.
  Allowed actions:
      - ask_interest
      - persuade
      - ask_name
      - fallback
      
       Output ONLY valid JSON:
    {
      "action":"ask_interest | persuade | ask_name | fallback",
      "reason":".... "
    }
    """
    
    user_input = f"Conversation state:{state} \nUser said: {user_msg}"
    
    reply = call_llm([
        {"role":"system", "content": system},
        {"role":"user","content":user_input}
    ])
    
    start = reply.find("{")
    end = reply.rfind("}")
    
    # if no json founf -> fallback 
    if start == -1 or end == -1:
        return{
            "action": "fallback",
            "reason":"LLM did not return JSON"
        }
    json_text = reply[start:end +1]
    
    try:
        return json.loads(json_text)
    except:
        return{
            "action":"fallback",
            "reason":"JSON parse error"
        }
# working agent 

def worker_agent(action, user_msg, emotion):
    system = f""" 
    You are a friendly sales agent 
    keep responses SHORT (one sentence).
    Respond in natural spoken English/Hinglish.
    User emotion:{emotion}
    Action:{action}
    """
    
    reply = call_llm([
        {"role": "system", "content": system},
        {"role":"user", "content": user_msg}
    ])
    
    return reply.strip()

# main entry used by fastapi bot 
def run_multi_agent(user_message, conversation_state="awaiting_interest", emotion="neutral"):
    plan = planner_agent(user_message, conversation_state)
    action = plan["action"]

    return worker_agent(action, user_message, emotion)