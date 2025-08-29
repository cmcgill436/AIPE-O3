import streamlit as st
from langchain_tavily import TavilySearch
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
import json
import os
from fpdf import FPDF
import io 
import docx 
import PyPDF2
import smtplib 
import ssl

load_dotenv()

# --- File persistence functions ---
REPORTS_FILE = "reports.json"
ALERTS_FILE = "alerts.json"

def load_reports():
    """Loads reports from a JSON file."""
    if os.path.exists(REPORTS_FILE):
        with open(REPORTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_reports(reports):
    """Saves reports to a JSON file."""
    with open(REPORTS_FILE, "w") as f:
        json.dump(reports, f)

def load_alert_keywords():
    """Loads alert keywords from a JSON file."""
    if os.path.exists(ALERTS_FILE):
        with open(ALERTS_FILE, "r") as f:
            return json.load(f)
    return []

def save_alert_keywords(keywords):
    """Saves alert keywords to a JSON file."""
    with open(ALERTS_FILE, "w") as f:
        json.dump(keywords, f)

# --- Alert Checking Logic ---
def check_for_alerts(keywords):
    if not keywords:
        return [] # Return an empty list to indicate no articles found
    
    new_articles = []
    tavily_search = TavilySearch(max_results=5)

    for keyword in keywords:
        search_query = f'"{keyword}" AND ("press release" OR "job posting") "last 7 days"'
        search_results = tavily_search.invoke(search_query)

        for result in search_results:
            new_articles.append({
                "keyword": keyword,
                "title": result['title'],
                "link": result['url'],
            })
    return new_articles

def send_email_alert(recipient_email, subject, body):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    
    if not sender_email or not sender_password:
        return False, "Email credentials not found in environment variables. Cannot send alert."

    smtp_server = "smtp.gmail.com"
    port = 587
    
    context = ssl.create_default_context()
    
    try:
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, f"Subject: {subject}\n\n{body}")
        return True, f"Alert email sent to {recipient_email}!"
    except Exception as e:
        return False, f"Failed to send email: {e}"


# Function to for CSS
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# PDF Generation Function
def create_pdf(report_content, company_name):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, f'Sales Insights Report - {company_name}', 0, 1, 'C')
    pdf.ln(10)
    
    pdf.set_font('Arial', '', 12)
    lines = report_content.split('\n')
    for line in lines:
        if line.strip():
            pdf.cell(0, 6, line.encode('latin-1', 'replace').decode('latin-1'), 0, 1)
        else:
            pdf.ln(3)
    
    pdf_output = io.BytesIO()
    pdf_string = pdf.output(dest='S').encode('latin-1')
    pdf_output.write(pdf_string)
    pdf_output.seek(0)
    return pdf_output.getvalue()

# Initialize Session State with persisted data 
if 'report_history' not in st.session_state:
    st.session_state.report_history = load_reports()
if 'current_report' not in st.session_state:
    if st.session_state.report_history:
        st.session_state.current_report = st.session_state.report_history[-1]
    else:
        st.session_state.current_report = None

if 'alert_keywords' not in st.session_state:
    st.session_state.alert_keywords = load_alert_keywords()

# Model and Tool
llm = ChatGroq(model="openai/gpt-oss-20b")
search_tool = TavilySearch(topic="general", max_results=2)

def generate_insights(company_name, product_name, company_url, company_competitors, product_category, value_proposition, target_customer, document_text=""):
    search_query = f"Site:{company_url} company strategy, leadership, competitors, business model"
    search_results = search_tool.invoke(search_query)

    messages = [
        SystemMessage(f"""You are a sales assistant with 15 years of experience. Your task is to analyze a prospective client and generate a one-page sales report. The report should be structured, concise, and actionable for a sales representative.
                      
        IMPORTANT:  Do not generate a title, header, or anything like 'Prepared for...' or 'One-Page Sales Report'."""),
        HumanMessage(content=f"""
        Company Info from Tavily: {search_results}
        Product Overview from Uploaded Document: {document_text}
    
        Company Name: {company_name}
        Company URL: {company_url}
        Product Name: {product_name}
        Product Category: {product_category}
        Value Proposition: {value_proposition}
        Competitors: {company_competitors}
        Target Customer Role: {target_customer}
        
        Generate a one-page sales report with the following sections. Ensure the information is relevant to selling {product_name} to the target company.
        1. Company Strategy:
           - A summary of the company's public strategy and goals, specifically in the {product_category} space.
           - Mention any key public statements, press releases, or job postings that hint at their technology stack or strategic direction.
           **Key Public Statements** (as a callout box for specific quotes)
        2. Competitor Analysis:
           - Any public mentions of the provided competitors ({company_competitors}) and how they relate to the target company.
           - Explain where our {product_name} might have an advantage based on the company's strategy.
           **Strategic Takeaway** (as a callout box for the final summary of this section)
        3. Leadership Insights:
           - Identify key leaders and decision-makers relevant to a sale in the {product_category} space.
           - Mention their recent public activity, such as quotes in articles or press releases.
           **Actionable Insight** (as a callout box for a list of insights)
        4. Value Proposition Alignment:
           - A brief summary explaining how our value proposition ("{value_proposition}") aligns with the target company's publicly stated strategy and goals.
           **Bottom Line** (as a callout box for the final summary)
        5. Source Links:
           - Provide a numbered list of all article links and sources used to generate the report.

        Ensure the final output is formatted in clear sections with bullet points.
        """)
    ]
    model_response = llm.invoke(messages)
    return model_response.content

# ============= UI ==============
st.title("Sales Agent 📊")
st.subheader("Generate a new report")
st.divider()

local_css("style.css")

# divider with custom color using markdown. Not using because I prefer the look of the divider
# st.markdown("<hr style='border: 2px solid #4B0082;'>", unsafe_allow_html=True)

# input fields
company_name = st.text_input("Company Name")
company_url = st.text_input("Company URL")
product_name = st.text_input("Product Name")
product_category = st.text_input("Product Category")
company_competitors = st.text_input("Company Competitors")
value_proposition = st.text_input("Value Proposition")
target_customer = st.text_input("Target Customer")

#file uploader
uploaded_file = st.file_uploader(
    "Upload a product overview sheet or deck (Optional)",
    type=["pdf", "docx", "pptx", "txt"] 
)

#generate report button
if st.button("Generate Report 📝"):
    if company_name and company_url:
        # --- Process the uploaded file if one exists ---
        document_text = ""
        if uploaded_file is not None:
            try:
                # Assuming you have installed the necessary libraries like PyPDF2 and python-docx
                file_bytes = uploaded_file.getvalue()
                
                if uploaded_file.type == "application/pdf":
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                    for page in pdf_reader.pages:
                        document_text += page.extract_text()
                elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                    import docx
                    doc = docx.Document(io.BytesIO(file_bytes))
                    for para in doc.paragraphs:
                        document_text += para.text + "\n"
                elif uploaded_file.type == "text/plain":
                    document_text = file_bytes.decode("utf-8")
                else:
                    st.warning("Unsupported file type. Please upload a PDF, DOCX, or TXT file.")
                    document_text = ""
            except Exception as e:
                st.error(f"Error processing file: {e}")
                document_text = ""

        with st.spinner("Generating Report..."):
            # Call the generate_insights function with the document text
           result = generate_insights(
                company_name, 
                product_name, 
                company_url, 
                company_competitors, 
                product_category, 
                value_proposition, 
                target_customer,
                document_text
            )
            
        new_report = {
                "company_name": company_name,
                "report_content": result
            }
        st.session_state.report_history.append(new_report)
        st.session_state.current_report = new_report
            
            # Save the reports after appending the new one
        save_reports(st.session_state.report_history)

        st.success(f"Report for {company_name} generated and saved!")
    else:
        st.warning("Please enter a company name and URL")

# Displays the Current Report on Main Page
if st.session_state.current_report:
    st.divider()
    st.markdown("### Report for " + st.session_state.current_report['company_name'])
    st.markdown(st.session_state.current_report['report_content'])
    
    # Generate PDF data
    pdf_data = create_pdf(st.session_state.current_report['report_content'], st.session_state.current_report['company_name'])

    st.download_button(
        label="Download as PDF",
        data=pdf_data,
        file_name=f"{st.session_state.current_report['company_name'].replace(' ', '_')}_report.pdf",
        mime="application/pdf",
        help="Download the currently displayed report as a PDF."
    )

def create_pdf(report_content, company_name):
    pdf = FPDF()
    
    # Set automatic page break, margin, and font - I don't think this is working properly. WIll need to work on this functionality further
    pdf.set_auto_page_break(True, 15)
    pdf.set_margins(15, 10, 15)
    
    pdf.add_page()
    
    # Title
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, f'Sales Insights Report - {company_name}', 0, 1, 'C')
    pdf.ln(10)
    
    # Body
    pdf.set_font('Arial', '', 12)
    lines = report_content.split('\n')
    for line in lines:
        # Check if line is a bullet point to preserve formatting
        if line.strip().startswith('•'):
            pdf.multi_cell(0, 5, txt=line)
        else:
            pdf.multi_cell(0, 5, txt=line)
        pdf.ln(2)
        
    pdf_output = io.BytesIO()
    pdf_output.write(pdf.output(dest='S').encode('latin-1', 'replace'))
    pdf_output.seek(0)
    return pdf_output.getvalue()    

# Sidebar for Past Reports
with st.sidebar:
    st.header("Past Reports 📂")
    if st.session_state.report_history:
        for i, report in enumerate(st.session_state.report_history):
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button(f"View {report['company_name']}", key=f"view_report_{i}"):
                    st.session_state.current_report = report
            with col2:
                if st.button("🗑️", key=f"delete_report_{i}"):
                    # Logic to delete the report will go here
                    st.session_state.report_history.pop(i)
                    save_reports(st.session_state.report_history)
                    # Check if the deleted report was the one currently displayed
                    if st.session_state.current_report and st.session_state.current_report['company_name'] == report['company_name']:
                        st.session_state.current_report = None
                    st.rerun()
    else:
        st.info("No reports have been generated yet.")

    # --- Alerts & Monitoring Section ---
    st.header("Alerts & Monitoring 🔔")
    
    st.session_state.alert_keywords = st.text_area(
        "Enter keywords to monitor (one per line)",
        value="\n".join(st.session_state.alert_keywords),
        key="alert_keywords_input"
    )

    recipient_email = st.text_input("Recipient Email for Alerts", key="recipient_email_input")

    if st.button("Save Alert Keywords"):
        keywords = [k.strip() for k in st.session_state.alert_keywords.split('\n') if k.strip()]
        save_alert_keywords(keywords)
        st.success("Keywords saved! Click 'Check for Alerts' to scan for new content.")

    if st.button("Check for Alerts"):
        keywords = load_alert_keywords()
        if not keywords:
            st.warning("Please save keywords to monitor first.")
        elif not recipient_email:
            st.warning("Please enter a recipient email.")
        else:
            with st.spinner("Checking for new articles..."):
                new_articles = check_for_alerts(keywords)

                if new_articles:
                    body = "New articles found for your monitored keywords:\n\n"
                    for article in new_articles:
                        body += f"Keyword: {article['keyword']}\nTitle: {article['title']}\nLink: {article['link']}\n\n"
                    
                    success, message = send_email_alert(recipient_email, "New Sales Alerts Found", body)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                else:
                    st.info("No new articles found for your keywords.")