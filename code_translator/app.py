import streamlit as st
from prompt import translate_code
from PIL import Image

st.set_page_config(layout="wide")

header = st.container()
with header:
    col4,col5,col6= st.columns([1,1,4])
    with col4:
        img = Image.open("about-visual.png")
        st.image(img)

st.header("Live Code Translation")

col1, col2 = st.columns([1,1])
flag = 0
with col1:
    st.header("Input Code")
    input_language = st.selectbox("Select Input Language", ["Python", "Java"])
    
    input_code = ""
    uploaded_file = st.file_uploader("Upload Code File", type=["py", "java", "txt"])
    
    if uploaded_file is not None:
        try:
            input_code = uploaded_file.getvalue().decode("utf-8")
            st.success("File uploaded successfully!")
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
    
    # Text area for direct code input (shows uploaded code if available)
    input_code = st.text_area(
        "Or paste the code here:", 
        value=input_code,
        height=200,
        key="input_area"
    )

    if st.button("Translate Code", use_container_width=True):
        flag = 1
        if input_code.strip():
            with st.spinner("Translating code..."):
                try:
                    translated_code = translate_code(
                        input_code, 
                    )
                    lines = translated_code.split('\n')
                    if len(lines) > 2:
                        filtered_code = '\n'.join(lines[1:-1])
                    else:
                        filtered_code = translated_code

                except Exception as e:
                    st.error(f"Translation error: {str(e)}")
with col2:
    st.header("Translated Code")
    output_language = st.selectbox("Select Target Language", ["Java", "C++", "Python"])
    
    if flag ==1:
        # Display translated code
        output_area = st.text_area(
            "Output Code:", 
            value=filtered_code, 
            height=200,
            key="output_area"
        )
        
        # Download button
        st.download_button(
            label="Download Translated Code",
            data=filtered_code,
            file_name=f"translated_code.{output_language.lower()}",
            mime="text/plain"
        )

# Optional: Add some status info at the bottom
#st.caption("Note: Translation quality may vary depending on code complexity")
