utf-8import streamlit as st
import pandas as pd
import duckdb
import tempfile
import uuid
import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from custos.pipeline import TextToSQLPipeline

st.set_page_config(
    page_title="Custos | Text-to-SQL",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Custos Text-to-SQL")
st.markdown("A highly-secure, read-only AI database assistant.")

@st.cache_resource
def get_pipeline():
    return TextToSQLPipeline()

pipeline = get_pipeline()


if "messages" not in st.session_state:
    st.session_state.messages = []
if "dynamic_components" not in st.session_state:
    st.session_state.dynamic_components = None
if "current_db_name" not in st.session_state:
    st.session_state.current_db_name = "Default Demo Database"


with st.sidebar:
    st.header("Database Configuration")
    st.write(f"**Current Dataset:** {st.session_state.current_db_name}")
    
    st.markdown("---")
    uploaded_files = st.file_uploader("Upload CSVs (Max 500MB)", type=["csv"], accept_multiple_files=True)
    if uploaded_files:
        if st.button("Load Dataset(s)"):
            with st.spinner("Introspecting schema and generating embeddings..."):
                session_id = str(uuid.uuid4())
                temp_db_path = os.path.join(tempfile.gettempdir(), f"custos_{session_id}.duckdb")
                conn = duckdb.connect(temp_db_path)
                
                db_names = []
                for uploaded_file in uploaded_files:
                    
                    df = pd.read_csv(uploaded_file)
                    
                    
                    conn.register("uploaded_table", df)
                    
                    
                    table_name = uploaded_file.name.replace(".csv", "").replace(" ", "_").lower()
                    
                    table_name = "".join(c for c in table_name if c.isalnum() or c == "_")
                    if not table_name:
                        table_name = "dataset"
                        
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM uploaded_table")
                    conn.unregister("uploaded_table")
                    db_names.append(uploaded_file.name)
                
                conn.close()
                
                
                db_url = f"duckdb:///{temp_db_path}"
                
                try:
                    st.session_state.dynamic_components = pipeline.setup_dynamic_db(db_url, session_id)
                    st.session_state.current_db_name = ", ".join(db_names)
                    st.session_state.messages = [] 
                    st.success(f"Successfully loaded `{len(db_names)}` dataset(s)!")
                except Exception as e:
                    st.error(f"Error loading database: {str(e)}")


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "data" in message and message["data"] is not None:
            st.dataframe(message["data"])
        if "sql" in message:
            with st.expander("View Generated SQL"):
                st.code(message["sql"], language="sql")
        if "confidence" in message:
            with st.expander("View Confidence Report"):
                st.json(message["confidence"])


if prompt := st.chat_input(f"Ask a question about {st.session_state.current_db_name}"):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Thinking... ⏳")
        
        try:
            
            chat_history = []
            for msg in st.session_state.messages[:-1]:
                if msg["role"] == "user":
                    chat_history.append({"role": "user", "content": msg["content"]})
                elif msg["role"] == "assistant" and "sql" in msg:
                    chat_history.append({
                        "role": "assistant", 
                        "content": f"I generated this SQL query for your previous request:\n```sql\n{msg['sql']}\n```"
                    })
            
            
            result = pipeline.run(
                user_question=prompt, 
                dynamic_components=st.session_state.dynamic_components,
                chat_history=chat_history
            )
            
            
            is_blocked = result.confidence_report.is_blocked
            is_ambiguous = result.is_ambiguous
            
            reply_text = ""
            if is_blocked:
                reply_text = f"🚨 **Query Blocked**\n\nThe query failed safety constraints or was blocked due to low confidence (Score: {result.confidence_report.final_score}/100)."
                st.error(reply_text)
            elif is_ambiguous:
                reply_text = f"🤔 **Ambiguous Request**\n\n{result.ambiguity_reason}"
                st.warning(reply_text)
            else:
                reply_text = f"✅ **Query Executed**\n\n{result.explanation}"
                st.success(reply_text)
            
            message_placeholder.markdown(reply_text)
            
            df = None
            if result.data:
                df = pd.DataFrame(result.data)
                st.dataframe(df)
                
            with st.expander("View Generated SQL"):
                st.code(result.sql, language="sql")
                
            with st.expander("View Confidence Report"):
                
                st.json(result.confidence_report.dict())
                
            st.session_state.messages.append({
                "role": "assistant",
                "content": reply_text,
                "data": df,
                "sql": result.sql,
                "confidence": result.confidence_report.dict()
            })
            
        except Exception as e:
            error_msg = f"An internal error occurred: {str(e)}"
            message_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
