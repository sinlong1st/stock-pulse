/** en/vi UI strings. Keys are dotted by screen. Brand words (StockPulse,
 * tickers) are intentionally not translated. Use {name} placeholders for params. */
type Lang = 'en' | 'vi';

export const STRINGS: Record<string, Record<Lang, string>> = {
  // common
  'common.cancel': { en: 'Cancel', vi: 'Huỷ' },
  'common.tryAgain': { en: 'Try again', vi: 'Thử lại' },
  'common.gotIt': { en: 'Got it', vi: 'Đã hiểu' },
  'common.notAdvice': { en: 'Not investment advice.', vi: 'Không phải lời khuyên đầu tư.' },

  // tabs
  'tab.Feed': { en: 'Feed', vi: 'Tin' },
  'tab.Report': { en: 'Report', vi: 'Báo cáo' },
  'tab.Predict': { en: 'Predict', vi: 'Dự đoán' },
  'tab.Watchlist': { en: 'Watchlist', vi: 'Theo dõi' },
  'tab.Settings': { en: 'Settings', vi: 'Cài đặt' },

  // feed
  'feed.title': { en: 'Feed', vi: 'Bảng tin' },
  'feed.sample': { en: 'STOCKPULSE · SAMPLE DATA', vi: 'STOCKPULSE · DỮ LIỆU MẪU' },
  'feed.all': { en: 'All', vi: 'Tất cả' },
  'feed.watchlist': { en: 'Watchlist', vi: 'Theo dõi' },
  'feed.macro': { en: 'Macro', vi: 'Vĩ mô' },
  'feed.search': { en: 'Search tickers, keywords…', vi: 'Tìm mã, từ khoá…' },
  'feed.fetching': { en: 'FETCHING LATEST', vi: 'ĐANG TẢI TIN MỚI' },
  'feed.errTitle': { en: 'Couldn’t reach the feed', vi: 'Không tải được tin' },
  'feed.caughtUp': { en: 'All caught up', vi: 'Đã xem hết' },
  'feed.caughtUpBody': {
    en: 'No alerts that matter right now. Pull to refresh.',
    vi: 'Chưa có tin quan trọng. Kéo xuống để làm mới.',
  },
  'feed.noMatch': { en: 'No matches', vi: 'Không có kết quả' },
  'feed.noMatchBody': { en: 'Nothing matches “{q}”.', vi: 'Không có gì khớp “{q}”.' },
  'feed.why': { en: 'WHY', vi: 'VÌ SAO' },

  // report
  'report.kicker': { en: 'BRIEFING', vi: 'BẢN TIN' },
  'report.title': { en: 'Report', vi: 'Báo cáo' },
  'report.whole': { en: 'Whole watchlist', vi: 'Cả danh mục' },
  'report.single': { en: 'Single stock', vi: 'Một cổ phiếu' },
  'report.tickerPlaceholder': {
    en: 'Ticker or company, e.g. WDC or Tesla',
    vi: 'Mã hoặc tên, vd WDC hoặc Tesla',
  },
  'report.generating': { en: 'Generating your briefing…', vi: 'Đang tạo bản tin…' },
  'report.generatingBody': {
    en: 'Reading the latest news and pricing your watchlist — a few seconds.',
    vi: 'Đang đọc tin mới và cập nhật giá — mất vài giây.',
  },
  'report.emptyTitle': { en: 'Today’s briefing', vi: 'Bản tin hôm nay' },
  'report.emptyBodyWatchlist': {
    en: 'An AI analyst reads the latest news and tells you what matters for your watchlist.',
    vi: 'AI đọc tin mới nhất và cho biết điều gì quan trọng với danh mục của bạn.',
  },
  'report.emptyBodyStock': {
    en: 'An AI analyst reads the latest news and tells you what matters for that stock.',
    vi: 'AI đọc tin mới nhất và cho biết điều gì quan trọng với cổ phiếu đó.',
  },
  'report.generate': { en: 'Generate briefing', vi: 'Tạo bản tin' },
  'report.takeaway': { en: 'TODAY’S TAKEAWAY', vi: 'ĐIỂM CHÍNH HÔM NAY' },
  'report.watchlist': { en: 'WATCHLIST', vi: 'DANH MỤC' },
  'report.footnote': { en: 'AI-generated. Not investment advice.', vi: 'Do AI tạo. Không phải lời khuyên đầu tư.' },
  'report.genErr': { en: 'Couldn’t generate the briefing.', vi: 'Không tạo được bản tin.' },

  // watchlist
  'wl.title': { en: 'Watchlist', vi: 'Danh mục' },
  'wl.count': { en: '{n} STOCKS', vi: '{n} CỔ PHIẾU' },
  'wl.label': { en: 'WATCHLIST', vi: 'DANH MỤC' },
  'wl.addPlaceholder': { en: 'Ticker or company, e.g. tesla', vi: 'Mã hoặc tên, vd tesla' },
  'wl.add': { en: 'Add', vi: 'Thêm' },
  'wl.remove': { en: 'Remove', vi: 'Xoá' },
  'wl.removeTitle': { en: 'Remove {ticker}?', vi: 'Xoá {ticker}?' },
  'wl.footer': {
    en: 'LONG-PRESS A ROW TO REMOVE · PULL TO REFRESH',
    vi: 'GIỮ MỘT DÒNG ĐỂ XOÁ · KÉO ĐỂ LÀM MỚI',
  },
  'wl.loadErr': { en: 'Couldn’t load your watchlist.', vi: 'Không tải được danh mục.' },
  'wl.notAdded': { en: 'Not added', vi: 'Chưa thêm' },
  'wl.addErr': { en: 'Couldn’t add', vi: 'Không thêm được' },
  'wl.removeErr': { en: 'Couldn’t remove', vi: 'Không xoá được' },

  // settings
  'set.title': { en: 'Settings', vi: 'Cài đặt' },
  'set.kicker': { en: 'ACCOUNT', vi: 'TÀI KHOẢN' },
  'set.notifications': { en: 'NOTIFICATIONS', vi: 'THÔNG BÁO' },
  'set.push': { en: 'Push to this phone', vi: 'Đẩy về điện thoại này' },
  'set.pushHint': { en: 'Alerts on your lock screen', vi: 'Cảnh báo hiện trên màn hình khoá' },
  'set.telegram': { en: 'Telegram', vi: 'Telegram' },
  'set.telegramOn': { en: 'Also send alerts to Telegram', vi: 'Gửi cảnh báo qua Telegram' },
  'set.telegramOff': { en: 'Not set up on the server', vi: 'Chưa cấu hình trên máy chủ' },
  'set.preferences': { en: 'PREFERENCES', vi: 'TUỲ CHỌN' },
  'set.language': { en: 'Language', vi: 'Ngôn ngữ' },
  'set.langTitle': { en: 'Output language', vi: 'Ngôn ngữ hiển thị' },
  'set.langBody': { en: 'Applies to alerts and briefings.', vi: 'Áp dụng cho cảnh báo và bản tin.' },
  'set.langErr': { en: 'Couldn’t change language', vi: 'Không đổi được ngôn ngữ' },
  'set.briefing': { en: 'Briefing schedule', vi: 'Lịch bản tin' },
  'set.briefingOff': { en: 'Off', vi: 'Tắt' },
  'set.briefingDaily': { en: 'Daily', vi: 'Hằng ngày' },
  'set.briefingDetail': {
    en: 'Morning {morning}, then every {hours}h until {until}, wrap {wrap} ({tz}).\n\nEdited on the server for now.',
    vi: 'Sáng {morning}, sau đó mỗi {hours} giờ đến {until}, tổng kết {wrap} ({tz}).\n\nHiện chỉnh trên máy chủ.',
  },
  'set.darkTheme': { en: 'Dark theme', vi: 'Giao diện tối' },
  'set.manageSub': { en: 'Manage subscription', vi: 'Quản lý gói' },
  'set.checkUpdates': { en: 'Check for updates', vi: 'Kiểm tra cập nhật' },
  'set.signOut': { en: 'Sign out', vi: 'Đăng xuất' },
  'set.deleteAccount': { en: 'Delete account', vi: 'Xoá tài khoản' },
  'set.disclaimer': { en: 'AI-generated summaries. Not investment advice.', vi: 'Tóm tắt do AI tạo. Không phải lời khuyên đầu tư.' },
  'set.upToDate': { en: 'Up to date', vi: 'Đã mới nhất' },
  'set.upToDateBody': { en: 'You’re on the latest version.', vi: 'Bạn đang dùng phiên bản mới nhất.' },
  'set.devMode': { en: 'Dev mode', vi: 'Chế độ dev' },
  'set.devModeBody': { en: 'OTA updates only apply in a real (EAS) build.', vi: 'Cập nhật OTA chỉ áp dụng cho bản build thật (EAS).' },
  'set.checkErr': { en: 'Couldn’t check', vi: 'Không kiểm tra được' },
  'set.checkErrBody': { en: 'Try again in a moment.', vi: 'Thử lại sau giây lát.' },

  // evaluation
  'eval.title': { en: 'AI accuracy', vi: 'Độ chính xác AI' },
  'eval.headline': { en: 'DIRECTIONAL ACCURACY', vi: 'ĐỘ CHÍNH XÁC HƯỚNG' },
  'eval.ofCalls': { en: 'of {n} calls\nscored against real moves', vi: 'trên {n} nhận định\nso với biến động thực' },
  'eval.pending': { en: 'PENDING', vi: 'CHỜ' },
  'eval.bullish': { en: '▲ BULLISH', vi: '▲ TĂNG' },
  'eval.bearish': { en: '▼ BEARISH', vi: '▼ GIẢM' },
  'eval.recent': { en: 'RECENT CALLS', vi: 'NHẬN ĐỊNH GẦN ĐÂY' },
  'eval.notEnough': { en: 'Not enough data yet', vi: 'Chưa đủ dữ liệu' },
  'eval.notEnoughBody': {
    en: 'Accuracy shows once the AI’s calls have had time to play out.',
    vi: 'Độ chính xác sẽ hiện khi các nhận định của AI có thời gian kiểm chứng.',
  },
  'eval.footnote': {
    en: 'Small sample — for reference only. Not investment advice.',
    vi: 'Mẫu nhỏ — chỉ để tham khảo. Không phải lời khuyên đầu tư.',
  },
  'eval.loadErr': { en: 'Couldn’t load accuracy.', vi: 'Không tải được độ chính xác.' },

  // alert detail
  'alert.title': { en: 'Alert', vi: 'Cảnh báo' },
  'alert.ago': { en: '{time} ago', vi: '{time} trước' },
  'alert.why': { en: 'WHY IT MATTERS', vi: 'VÌ SAO QUAN TRỌNG' },
  'alert.affected': { en: 'AFFECTED TICKERS', vi: 'CỔ PHIẾU LIÊN QUAN' },
  'alert.open': { en: 'Open', vi: 'Mở' },
  'alert.disclaimer': {
    en: 'AI-generated summary. Not investment advice — verify against the source before acting.',
    vi: 'Tóm tắt do AI tạo. Không phải lời khuyên đầu tư — hãy kiểm chứng nguồn trước khi hành động.',
  },
};
