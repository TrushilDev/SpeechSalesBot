# main.py
from fastapi import FastAPI
from leadGathering import (
    router as lead_router,
    _initiate_call as initiate_lead_call,
    # start_excel_call_list as lead_excel_call_list,
    )
from speechLinkShare import (
    router as link_router,
    _initiate_call as initiate_link_call,
    start_excel_call_list as link_excel_call_list,
    )
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# OUTBOUND CALLBACK APIs

# Lead gathering end point
@app.get("/start-outbound-call-leadGathering")
def start_outbound_call_lead(phone: str, storage: str = "supabase"):
    if not phone:
        return {"error": "Phone missing"}
    return initiate_lead_call(phone,storage)

# link share of the product
@app.get("/start-outbound-call-linkShare")
def start_outbound_call_link(phone: str):
    if not phone:
        return {"error": "Phone missing"}
    return initiate_link_call(phone)

# bulk calling from the excel

# lead gathering bulk
# @app.get("/start-excel-call-list-leadGathering")   
# def start_excel_call_list_lead():
#     """
#     Triggers the Excel call list logic from leadGathering.py
#     Internally uses customers.xlsx from that script's folder.
#     """
#     return lead_excel_call_list() 

# link share product bulk
# @app.get("/start-excel-call-list-linkShare")      
# def start_excel_call_list_link():
#     """
#     Triggers the Excel call list logic from speechLinkShare.py
#     """
#     return link_excel_call_list() 



# MOUNT TWILIO WEBHOOKS
app.include_router(lead_router, prefix="/lead")
app.include_router(link_router, prefix="/link")

# START SERVER
# if __name__ == "__main__":
#     import uvicorn
#     print("🔥 Server running at http://localhost:8000")
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    import uvicorn
    print("🔥 Server running at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
