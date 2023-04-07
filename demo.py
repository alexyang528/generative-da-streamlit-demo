import streamlit as st
import openai
import yext
import json


# Configure Page
st.set_page_config(
    page_title="Generative Direct Answers Demo",
    page_icon=":mag:",
    initial_sidebar_state="expanded",
    layout="wide",
)
st.title("Generative Direct Answers Demo")

# Configure OpenAI
openai.api_key = st.secrets.openai_api_key

@st.cache_data
def call_chat_gpt(prompt):

    try:
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}]
        )
    except openai.error.InvalidRequestError as error:
        st.error(f"{error}")
        st.stop()

    answer = completion.choices[0].message
    return answer

# Configure Yext Search Experience
st.sidebar.title("Settings")
st.sidebar.markdown("## Search Experience:")
account = st.sidebar.selectbox(label="Experience", options=[secret for secret in st.secrets if secret != "openai_api_key"])
vertical = st.sidebar.selectbox(label="Vertical", options=st.secrets[account]["vertical_keys"])
locale = st.sidebar.selectbox(label="Locale", options=st.secrets[account]["locales"])

@st.cache_resource
def yext_client(account):
    api_key = st.secrets[account]["api_key"]
    return yext.YextClient(api_key, "20230101")

@st.cache_data
def yext_search(query, vertical, locale, _client):

    raw_results = _client.search_answers_vertical(
        query=query,
        experience_key=st.secrets[account]["experience_key"],
        vertical_key=vertical,
        locale=locale,
    )

    if len(raw_results["response"]["modules"]) == 0:
        return []

    # Extract just the data from each result
    results = [r["data"] for r in raw_results["response"]["modules"][0]["results"]]
    
    return results, raw_results


# Configure Search Parameters
st.sidebar.markdown("## Search Parameters:")
query = st.sidebar.text_input(label="Query")
instructions = st.sidebar.text_area(label="Instructions", value="""As a BOT, your job is to use ONLY the results above to answer the HUMAN's question. You return a JSON object containing a RESPONSE (which can contain any valid markdown), and a SOURCE.
    - Look at the HUMAN's search query.
    - IF the answer to the question is in the results above, then rewrite the result to best answer the question in the RESPONSE. Do not reference any information
    outside of the above results.
    - the SOURCE should be a JSON object of any number of results from which you got the answer. For eaach result, include the ID of the result if present, and the field used to construct the answer.
    A successful result should look like:
    {{"response": "This is the answer to the question", "source": [{{"id": "123", "answerField": "c_body"}}, {{"id": "456", "answerField": "c_content"}}]}}
    - BUT if the answer is not available in the context above - which often it isn't - simply return None for response and an empty list for source.
    An unsuccessful result should look like:
    {{"response": None, "source": []}}""")
num_results = st.sidebar.number_input(label="Number of Results", value=3, min_value=1, max_value=10)


def construct_prompt(query, results, fields, instructions, num_results):

    def _construct_result_prompt(results, fields, num_results):
        if len(results) < num_results:
            num_results = len(results)

        filtered_results = []
        for result in results:
            filtered_results.append({k: v for k, v in result.items() if k in fields})

        results_prompt = ""
        for i in range(num_results):
            results_prompt += "## RESULT:\n"
            for key, value in filtered_results[i].items():
                results_prompt += f"- {key}: {value}\n"
        return results_prompt

    prompt = f"# RESULTS BEGIN\n{_construct_result_prompt(results, fields, num_results)}# RESULTS END\n# INSTRUCTIONS\n{instructions}\n# CONVERSATION\nHUMAN: {query}\nBOT:"

    return prompt

def render_result(result, display_fields):
    out = f"### {result.get(display_fields[0], '')}\n"

    for field in display_fields[1:]:
        value = result.get(field, '')
        display_value = value[:500] + "..." if len(value) > 500 else value
        out += f"**{field}**: {display_value}\n\n"
    
    return out


client = yext_client(account)
if not query:
    st.info("Enter a query to begin.")
    st.stop()

results, raw_results = yext_search(query, vertical, locale, client)

if len(results) == 0:
    st.warning("No results found.")
    st.stop()

c1, _, c2 = st.columns((1, 0.05, 1))
with c1:
    default_document_fields = st.secrets[account]["default_document_fields"] if "default_document_fields" in st.secrets[account] else []
    display_fields = st.multiselect(
        label="Display Fields",
        options=results[0].keys(),
        default=["name", "id"] + default_document_fields,
    )
    if not display_fields:
        st.warning("Select at least one display field to continue.")
        st.stop()

    st.markdown("## Results:")
    for result in results:
        st.info(render_result(result, display_fields))
    
    with st.expander("API Response"):
        st.json(raw_results)

with c2: 
    default_document_fields = st.secrets[account]["default_document_fields"] if "default_document_fields" in st.secrets[account] else []
    document_fields = st.multiselect(
        label="Document Search Fields",
        options=results[0].keys(),
        default=["id"] + default_document_fields,
    )

    st.markdown("## GPT Direct Answer:")
    if not document_fields:
        st.warning("Select at least one document field to continue.")
        st.stop()

    prompt = construct_prompt(query, results, document_fields, instructions, num_results)
    answer = call_chat_gpt(prompt)
    answer_json = json.loads(answer["content"])
    st.info(answer_json["response"])

    st.markdown("## Source:")
    if answer_json["source"]:
        for source in answer_json["source"]:
            for result in results:
                if result["id"] == source["id"]:
                    st.info(render_result(result, display_fields))
                    break
    else:
        st.info("No source provided.")

    with st.expander("Prompt"):
        st.code(prompt)
