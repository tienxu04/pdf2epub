import streamlit as st
import google.generativeai as genai
import fitz  # PyMuPDF
from PIL import Image
from docx import Document
import io
import time
import os

# ==========================================
# CẤU HÌNH GIAO DIỆN STREAMLIT
# ==========================================
st.set_page_config(page_title="PDF to Word OCR", page_icon="📚", layout="centered")

st.title("📚 Tool OCR Tiếng Việt (PDF to Word)")
st.caption("Sử dụng sức mạnh của Gemini AI - Thiết kế bởi bạn!")

# ==========================================
# LỚP QUẢN LÝ XOAY VÒNG API KEY (KEY ROTATOR)
# ==========================================
class KeyRotator:
    def __init__(self, keys_text):
        # Lọc các key rỗng và xóa khoảng trắng
        raw_keys = keys_text.split('\n')
        self.keys = [k.strip() for k in raw_keys if k.strip()]
        self.index = 0
        
    def get_key(self):
        if not self.keys:
            return None
        key = self.keys[self.index]
        # Chuyển sang key tiếp theo cho lần gọi tới
        self.index = (self.index + 1) % len(self.keys)
        return key
    
    def count(self):
        return len(self.keys)

# ==========================================
# HÀM GỌI GEMINI API OCR TRANG ẢNH
# ==========================================
def process_page_ocr(img, rotator, max_retries=3):
    prompt = """Bạn là một chuyên gia OCR tiếng Việt. Hãy trích xuất chính xác toàn bộ văn bản từ hình ảnh này.
Yêu cầu bắt buộc:
1. Giữ nguyên từng từ, dấu câu của bản gốc.
2. Giữ nguyên việc ngắt dòng, phân đoạn (xuống dòng như trong ảnh).
3. Tuyệt đối KHÔNG thêm bất kỳ bình luận, giải thích, hay lời chào nào. Chỉ trả về đúng văn bản được trích xuất."""

    for attempt in range(max_retries):
        current_key = rotator.get_key()
        if not current_key:
            return "[Lỗi: Không có API Key]"

        try:
            genai.configure(api_key=current_key)
            # Dùng model flash để tối ưu tốc độ (có thể đổi sang gemini-2.5-flash nếu có)
            model = genai.GenerativeModel("gemini-1.5-flash") 
            response = model.generate_content([prompt, img])
            return response.text
            
        except Exception as e:
            # Nếu gặp lỗi Rate Limit hoặc quá tải, nghỉ 2s rồi thử key tiếp theo
            time.sleep(2)
            if attempt == max_retries - 1:
                return f"\n[LỖI OCR TRANG NÀY: {str(e)}]\n"

# ==========================================
# HÀM TẠO FILE DOCX
# ==========================================
def create_docx(text_content):
    doc = Document()
    # Tách văn bản thành các đoạn và thêm vào Word
    for paragraph in text_content.split('\n'):
        if paragraph.strip():
            doc.add_paragraph(paragraph)
        else:
            doc.add_paragraph("") # Giữ nguyên khoảng trống
    
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

# ==========================================
# SIDEBAR: CẤU HÌNH API KEYS
# ==========================================
with st.sidebar:
    st.header("⚙️ Cấu hình API")
    st.markdown("Nhập 5 API Keys của Gemini vào đây, mỗi key 1 dòng. Hệ thống sẽ tự động xoay tua để tránh lỗi Rate Limit.")
    keys_input = st.secrets.get("GEMINI_KEYS", "")
    rotator = KeyRotator(keys_input)
    
    if rotator.count() > 0:
        st.success(f"Đã nhận diện {rotator.count()} API Keys.")
    else:
        st.warning("Vui lòng nhập ít nhất 1 API Key để bắt đầu.")

# ==========================================
# GIAO DIỆN CHÍNH: UPLOAD & XỬ LÝ
# ==========================================
uploaded_files = st.file_uploader("Kéo thả các file PDF vào đây (Khuyên dùng: Dưới 20 trang/file)", 
                                  type=["pdf"], 
                                  accept_multiple_files=True)

if uploaded_files and rotator.count() > 0:
    st.write("---")
    
    for uploaded_file in uploaded_files:
        st.subheader(f"📄 Đang xử lý: `{uploaded_file.name}`")
        
        # Đọc PDF từ bộ nhớ RAM
        pdf_bytes = uploaded_file.getvalue()
        pdf_document = fitz.open("pdf", pdf_bytes)
        total_pages = len(pdf_document)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        full_text = ""
        
        # Xử lý từng trang
        for page_num in range(total_pages):
            status_text.text(f"Đang OCR trang {page_num + 1} / {total_pages}...")
            
            # 1. Convert trang PDF thành hình ảnh
            page = pdf_document.load_page(page_num)
            pix = page.get_pixmap(dpi=150) # DPI 150 đủ nét cho OCR và tối ưu dung lượng
            img_data = pix.tobytes("jpeg")
            img = Image.open(io.BytesIO(img_data))
            
            # 2. Gọi Gemini bóc tách chữ
            page_text = process_page_ocr(img, rotator)
            full_text += page_text + "\n\n"
            
            # Cập nhật thanh tiến trình
            progress_bar.progress((page_num + 1) / total_pages)
            
        status_text.text("✅ Đã OCR xong! Đang đóng gói file Word...")
        
        # 3. Tạo file Docx
        docx_bytes = create_docx(full_text)
        
        # 4. Tạo nút Download với tên file như input
        base_name = os.path.splitext(uploaded_file.name)[0]
        output_filename = f"{base_name}.docx"
        
        st.download_button(
            label=f"⬇️ Nhấn để tải về: {output_filename}",
            data=docx_bytes,
            file_name=output_filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key=uploaded_file.name # Đảm bảo key độc nhất cho mỗi nút
        )
        st.write("---")
