# Email Watcher - Tự động xử lý nội dung email

**Phiên bản mới nhất: 2.0 **

Đây là một dự án Python giúp bạn tự động xử lý nội dung email từ Netflix (cập nhật hộ gia đình, mã OTP) và Ngân hàng (thông báo biến động số dư).

## Tính năng

*   **Tự động cập nhật hộ gia đình Netflix:** Khi nhận được email yêu cầu cập nhật hộ gia đình từ Netflix, bot sẽ tự động mở liên kết và xác nhận giúp bạn, **loại bỏ bước xác nhận thủ công qua SMS hoặc Email**.
*   **Tự động lấy mã OTP Netflix:** Khi nhận được email chứa mã OTP đăng nhập hoặc mã OTP tạm thời, bot sẽ tự động trích xuất và gửi mã OTP cho bạn qua Telegram.
*   **Thông báo biến động số dư Ngân Hàng (Hiện tại là Timo Bank):** Khi nhận được email thông báo biến động số dư tài khoản của Timo, bot sẽ tự động trích xuất thông tin giao dịch (số tiền tăng/giảm, số dư hiện tại, mô tả, thời gian) và gửi cho bạn qua Telegram.
*   **Hỗ trợ bật/tắt module:** Bạn có thể dễ dàng bật/tắt chức năng xử lý email Netflix hoặc Timo thông qua biến môi trường.
*   **Lấy danh sách người nhận từ Google Sheets:** Danh sách email và ID Telegram được lưu trữ trên Google Sheets, dễ dàng chỉnh sửa và cập nhật.
*   **Gửi thông báo qua Telegram:** Bot sử dụng Telegram để gửi thông báo cho người dùng.
*   **Sử dụng Selenium để tương tác với trang web:** Bot sử dụng Selenium để tự động mở liên kết và thao tác trên trang web Netflix.
*   **Xử lý lỗi và thử lại:** Bot có khả năng xử lý lỗi và tự động thử lại khi gửi tin nhắn Telegram thất bại.
*   **Logging:** Bot ghi lại nhật ký hoạt động, giúp bạn dễ dàng theo dõi và khắc phục sự cố.

## Yêu cầu

*   Python 3.7+
*   Các thư viện Python (cho phiên bản tự build):
    *   `imaplib`
    *   `email`
    *   `re`
    *   `time`
    *   `os`
    *   `requests`
    *   `html2text`
    *   `selenium`
    *   `google-api-python-client`
    *   `logging`

## Cài đặt

### Cách 1: Sử dụng Docker Image build sẵn (Phiên bản 2.0)

**Lưu ý:** Đây là phiên bản đã được build sẵn và dễ dàng cài đặt.

1.  Pull image từ Docker Hub:

    ```bash
    docker pull cpanel10x/netflix-watcher:2.0
    ```

2.  Tạo file `docker-compose.yml` với nội dung sau:

    ```yaml
    version: "3"

    services:
      netflix_watcher:
        image: cpanel10x/netflix-watcher:2.0
        container_name: netflix_watcher
        restart: always
        environment:
          - EMAIL_IMAP=<your_imap_server>
          - EMAIL_LOGIN=<your_email_address>
          - EMAIL_PASSWORD=<your_email_password>
          - NETFLIX_EMAIL_SENDERS=<netflix_email_sender1>,<netflix_email_sender2>
          - TELEGRAM_TOKEN=<your_telegram_bot_token>
          - TELEGRAM_ADMIN_UID=<your_telegram_user_id>
          - SPREADSHEET_ID=<your_google_spreadsheet_id> # Có thể bỏ qua nếu không dùng
          - RANGE_NAME=<your_sheet_name>!<your_range> # Có thể bỏ qua nếu không dùng
          - GOOGLE_SHEETS_API_KEY=<your_google_sheets_api_key> # Có thể bỏ qua nếu không dùng
          - ENABLE_NETFLIX_MODULE=true # Có thể bỏ qua nếu không dùng, mặc định là true
          - ENABLE_CAKE_MODULE=false # Có thể bỏ qua, mặc định là false
          - CAKE_EMAIL_SENDERS= # Có thể bỏ qua nếu không dùng

    ```

    **Lưu ý:**

    *   Thay thế các giá trị mẫu (e.g., `<your_imap_server>`, `<your_email_address>`) bằng thông tin của bạn.
    *   `EMAIL_LOGIN` là email mà bạn dùng để nhận thông báo từ Netflix.
    *   `NETFLIX_EMAIL_SENDERS`: Địa chỉ email gửi thông báo từ Netflix. Mặc định là `info@account.netflix.com`.
    *   Các thông số `SPREADSHEET_ID`, `RANGE_NAME`, `API_KEY`, `ENABLE_CAKE_MODULE`, `CAKE_EMAIL_SENDERS` có thể bỏ qua trong phiên bản 2.0.
    *   Để lấy `TELEGRAM_TOKEN`, bạn cần tạo một bot Telegram thông qua BotFather.
    *   Để lấy `TELEGRAM_ADMIN_UID`, sử dụng bot `@userinfobot`.
    *   Phân quyền cho `http://netflix_watcher_selenium:4444/wd/hub` truy cập vào tài khoản google của bạn. Nếu chạy trên local bỏ phần này và tự phân quyền khi có thông báo
    *   Đảm bảo rằng tài khoản email của bạn đã được kích hoạt "Truy cập vào ứng dụng kém an toàn hơn" (Less secure app access).

3.  Chạy Docker Compose:

    ```bash
    docker-compose up -d
    ```

### Cách 2: Tự build từ source code (Phiên bản 4.5)

**Lưu ý:** Đây là phiên bản mới nhất, cho phép bạn tùy chỉnh và cập nhật mã nguồn.

1.  **Clone repository:**

    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Cài đặt các thư viện cần thiết:**

    ```bash
    pip install -r requirements.txt
    ```

3.  **Tạo file `.env` và cấu hình các biến môi trường:**

    ```
    EMAIL_IMAP=<your_imap_server>
    EMAIL_LOGIN=<your_email_address>
    EMAIL_PASSWORD=<your_email_password>
    NETFLIX_EMAIL_SENDERS=<netflix_email_sender1>,<netflix_email_sender2> (Mặc định: '', các địa chỉ email gửi từ netflix, cách nhau bằng dấu phẩy)
    CAKE_EMAIL_SENDERS=<cake_email_sender1>,<cake_email_sender2> (Mặc định: '', các địa chỉ email gửi từ cake, cách nhau bằng dấu phẩy)
    TELEGRAM_TOKEN=<your_telegram_bot_token>
    SPREADSHEET_ID=<your_google_spreadsheet_id>
    RANGE_NAME=<your_sheet_name>!<your_range> (Ví dụ: Sheet1!A2:B)
    GOOGLE_SHEETS_API_KEY=<your_google_sheets_api_key>
    TELEGRAM_ADMIN_UID=<your_telegram_user_id> (ID Telegram của bạn)
    ENABLE_NETFLIX_MODULE=true (Bật/tắt module Netflix, mặc định: true)
    ENABLE_CAKE_MODULE=true (Bật/tắt module Cake, mặc định: true)
    ```

    **Lưu ý:**

    *   Thay thế các giá trị mẫu bằng thông tin của bạn.
    *   `EMAIL_LOGIN` là email mà bạn dùng để nhận thông báo từ Netflix và Cake.
    *   `NETFLIX_EMAIL_SENDERS` và `CAKE_EMAIL_SENDERS`: Nếu bạn không muốn sử dụng module nào, hãy để trống giá trị. Mặc định là `info@account.netflix.com` cho Netflix.
    *   Để lấy `TELEGRAM_TOKEN`, bạn cần tạo một bot Telegram thông qua BotFather.
    *   Để lấy `SPREADSHEET_ID`, `RANGE_NAME` và `GOOGLE_SHEETS_API_KEY`, bạn cần tạo một Google Sheets công khai và kích hoạt Google Sheets API.
    *   Đảm bảo rằng tài khoản email của bạn đã được kích hoạt "Truy cập vào ứng dụng kém an toàn hơn" (Less secure app access).

4.  **Cấu hình Google Sheets (Cho `SPREADSHEET_ID`, `RANGE_NAME` và `GOOGLE_SHEETS_API_KEY`)**

    *   Tạo một Google Sheets mới hoặc sử dụng sheet hiện có.
    *   **Nội dung mẫu:**

        | email                | telegram_id     | Note        | Date       |
        | -------------------- | --------------- | ------------- | ---------- |
        | abc@abc.com          | -4218646176    | netflix email   | 28/05/2024 |
        | abc2@abc.com        | -4218646176    | timobank        | 30/10/2024 |
       

        *   **Cột A (email):** Địa chỉ email của chủ hộ Netflix hoặc email chủ tài khoản nhận mail biến động số dư.
        *   **Cột B (telegram_id):** ID Telegram của người dùng tương ứng.
        *   **Cột C và D:** Thông tin thêm (tùy chọn).
    *   Lấy `SPREADSHEET_ID` từ URL của Google Sheets (phần giữa `/d/` và `/edit`).
    *   `RANGE_NAME` là tên sheet và vùng dữ liệu. Ví dụ: `Sheet1!A2:B` (lấy dữ liệu từ cột A đến cột B, bắt đầu từ dòng 2).
    *   Làm theo hướng dẫn của Google để kích hoạt Google Sheets API và lấy `GOOGLE_SHEETS_API_KEY`.

5.  **Tạo file `docker-compose.yml`**

    ```
        version: "3.9"

        services:
          netflix_watcher:
            build: .
            container_name: netflix_watcher
            restart: always
            environment:
              - EMAIL_IMAP=${EMAIL_IMAP}
              - EMAIL_LOGIN=${EMAIL_LOGIN}
              - EMAIL_PASSWORD=${EMAIL_PASSWORD}
              - NETFLIX_EMAIL_SENDERS=${NETFLIX_EMAIL_SENDERS}
              - CAKE_EMAIL_SENDERS=${CAKE_EMAIL_SENDERS}
              - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
              - SPREADSHEET_ID=${SPREADSHEET_ID}
              - RANGE_NAME=${RANGE_NAME}
              - GOOGLE_SHEETS_API_KEY=${API_KEY}
              - TELEGRAM_ADMIN_UID=${TELEGRAM_ADMIN_UID}
              - ENABLE_NETFLIX_MODULE=${ENABLE_NETFLIX_MODULE}
              - ENABLE_CAKE_MODULE=${ENABLE_CAKE_MODULE}
            depends_on:
              - netflix_watcher_selenium

          netflix_watcher_selenium:
            image: selenium/standalone-chrome:latest
            container_name: netflix_watcher_selenium
            shm_size: '2g'
            restart: always
    ```

6.  **Build và chạy Docker Compose:**

    ```bash
    docker-compose up -d --build
    ```


## Liên hệ

Nếu bạn có bất kỳ câu hỏi hoặc góp ý nào, vui lòng liên hệ qua Telegram: @cpanel10x

## Giấy phép

MIT License

## Lời cảm ơn (Từ phiên bản cũ)

This project was inspired by the need to simplify the Netflix Household update process.  It aims to save users time and effort by automating the email confirmation step. (Dự án này được lấy cảm hứng từ nhu cầu đơn giản hóa quy trình cập nhật Hộ gia đình Netflix. Nó nhằm mục đích tiết kiệm thời gian và công sức của người dùng bằng cách tự động hóa bước xác nhận email.)
Base on: https://github.com/jakubfrasunek/netflixWatcher. Thanks @jakubfrasunek
