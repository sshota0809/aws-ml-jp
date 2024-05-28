import re
import streamlit as st
from langgraph.graph import END, StateGraph
from utils import advanced_rag
from utils.advanced_rag import (
    GraphState,
    retrieve,
    generate,
)
from utils.s3_utils import generate_presigned_url_from_s3_uri

ja2en = {"なし": None, "クエリ拡張": "generate_queries", "検索結果の関連度評価": "grade_documents"}

def generate_rag_answer(query, settings):
    preretrieval_method = ja2en[settings["preretrieval_method"]]
    postretrieval_method = ja2en[settings["postretrieval_method"]]

    inputs = {"keys": {"question": query, "settings": settings}}
    if preretrieval_method == "generate_queries":
        inputs["keys"]["n_queries"] = 3

    workflow = StateGraph(GraphState)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)
    app = None
    if preretrieval_method is None and postretrieval_method is None:
        # Naive RAG
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", END)
        app = workflow.compile()
    elif preretrieval_method is not None and postretrieval_method is None:
        # Pre-retrieval Only
        workflow.add_node(preretrieval_method, getattr(advanced_rag, preretrieval_method))

        workflow.set_entry_point(preretrieval_method)
        workflow.add_edge(preretrieval_method, "retrieve")
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", END)
        app = workflow.compile()
    elif preretrieval_method is None and postretrieval_method is not None:
        # Post-retrieval Only
        workflow.add_node(postretrieval_method, getattr(advanced_rag, postretrieval_method))

        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", postretrieval_method)
        workflow.add_edge(postretrieval_method, "generate")
        workflow.add_edge("generate", END)
        app = workflow.compile()
    elif preretrieval_method is not None and postretrieval_method is not None:
        # Both Pre-retrieval and Post-retrieval
        workflow.add_node(preretrieval_method, getattr(advanced_rag, preretrieval_method))
        workflow.add_node(postretrieval_method, getattr(advanced_rag, postretrieval_method))

        workflow.set_entry_point(preretrieval_method)
        workflow.add_edge(preretrieval_method, "retrieve")
        workflow.add_edge("retrieve", postretrieval_method)
        workflow.add_edge(postretrieval_method, "generate")
        workflow.add_edge("generate", END)
        app = workflow.compile()

    with st.spinner("Generating answer..."):
        for output in app.stream(inputs):
            for key, value in output.items():
                if key == "generate_queries":
                    columns = st.columns(value["keys"]["n_queries"] + 1)
                    for i, column in enumerate(columns):
                        with column:
                            st.markdown(f"""
<div style="background-color:#f1f1f1; padding:0px 10px; border-radius:12px; font-size:12px;">
{value["keys"]["queries"][i]}
</div>
""", unsafe_allow_html=True)
                    st.markdown("")
                elif key == "retrieve":
                    documents = value["keys"]["documents"]
                    with st.popover(f"{len(documents)}件のユニークなチャンク"):
                        show_documents(documents)
                elif key == "grade_documents":
                    documents = value["keys"]["documents"]
                    with st.popover(f"{len(documents)}件の関連度の高いチャンク"):
                        show_documents(documents)
    
    return value
    #st.write(value["keys"]["generation"])
    #for chunk in value["keys"]["generation"]:
    #    yield chunk
    
    # レスポンスをチャンクで処理
    #for chunk in response:
    #    yield chunk["choices"][0]["text"]

def show_documents(documents):
    for i, document in enumerate(documents):
        document_title = document.metadata["title"]
        document_id = document.metadata["document_attributes"]["_source_uri"]
        document_excerpt = document.metadata["excerpt"]
        
        st.markdown(f"##### {document_title}")
        if document_id.startswith("https://s3."):
            pattern = r"https://s3\.([a-z]{2}(?:-gov)?-[a-z]+-\d)\.amazonaws\.com/"
            document_id = re.sub(pattern, "s3://", document_id)

        if document_id.startswith("s3://"):
            # S3 URIの場合、presigned URLを発行してリンクを表示
            presigned_url = generate_presigned_url_from_s3_uri(document_id)
            if presigned_url:
                st.markdown(f"{document_id} [\[View Document\]]({presigned_url})")
            else:
                st.markdown(f"{document_id}")
        else:
            st.write(f"Document ID: {document_id}")
        st.caption(document_excerpt.replace("\n", ""))
