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
  'report.regenerate': { en: 'Re-generate', vi: 'Tạo mới' },
  'report.takeaway': { en: 'TODAY’S TAKEAWAY', vi: 'ĐIỂM CHÍNH HÔM NAY' },
  'report.watchlist': { en: 'WATCHLIST', vi: 'DANH MỤC' },
  'report.sources': { en: 'SOURCES', vi: 'NGUỒN' },
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

  // terminal loading screen (Report + Predict)
  'loader.channel': { en: 'STOCKPULSE // ANALYST LINK', vi: 'STOCKPULSE // KÊNH PHÂN TÍCH' },
  'loader.active': { en: 'ACTIVE', vi: 'ĐANG CHẠY' },
  'loader.stream': { en: 'LIVE STREAM', vi: 'LUỒNG TRỰC TIẾP' },
  'loader.rec': { en: 'REC', vi: 'REC' },
  'loader.working': { en: 'Working', vi: 'Đang xử lý' },
  'loader.complete': { en: 'COMPLETE', vi: 'HOÀN TẤT' },
  'loader.doNotClose': { en: 'DO NOT CLOSE THE APP', vi: 'ĐỪNG ĐÓNG ỨNG DỤNG' },
  'loader.abort': { en: 'ABORT SEQUENCE', vi: 'HUỶ TIẾN TRÌNH' },

  // report loader
  'loader.report.scramble': { en: 'GENERATING', vi: 'ĐANG TẠO' },
  'loader.report.headline': { en: 'YOUR BRIEFING', vi: 'BẢN TIN CỦA BẠN' },
  'loader.report.kicker': { en: 'BRIEFING · ON DEMAND', vi: 'BẢN TIN · THEO YÊU CẦU' },
  // Order matches REPORT_STAGES: news · prices · analyze · compose
  'loader.report.step1': { en: 'Reading the wire', vi: 'Đọc tin mới' },
  'loader.report.step2': { en: 'Pricing your watchlist', vi: 'Cập nhật giá danh mục' },
  'loader.report.step3': { en: 'Writing the briefing', vi: 'Soạn bản tin' },
  'loader.report.step4': { en: 'Adding prices & earnings', vi: 'Thêm giá & kết quả KD' },
  'loader.report.log1': { en: 'pulling headlines · reuters', vi: 'tải tiêu đề · reuters' },
  'loader.report.log2': { en: 'dedupe wire copy', vi: 'lọc tin trùng lặp' },
  'loader.report.log3': { en: 'price check · watchlist', vi: 'kiểm tra giá · danh mục' },
  'loader.report.log4': { en: 'sentiment pass', vi: 'phân tích sắc thái' },
  'loader.report.log5': { en: 'rank signal strength', vi: 'xếp hạng tín hiệu' },
  'loader.report.log6': { en: 'cross-ref filings', vi: 'đối chiếu hồ sơ' },
  'loader.report.log7': { en: 'watchlist delta computed', vi: 'tính biến động danh mục' },
  'loader.report.log8': { en: 'drafting briefing', vi: 'soạn thảo bản tin' },

  // predict loader
  'loader.predict.scramble': { en: 'PREDICTING', vi: 'ĐANG DỰ ĐOÁN' },
  'loader.predict.kicker': { en: 'AI · FORWARD-LOOKING', vi: 'AI · DỰ BÁO' },
  'loader.predict.headline': { en: 'THE READ', vi: 'NHẬN ĐỊNH' },
  // Order matches PREDICT_STAGES: resolve · prices · news · analyze
  'loader.predict.step1': { en: 'Finding the stock', vi: 'Tìm cổ phiếu' },
  'loader.predict.step2': { en: 'Price history & signals', vi: 'Dữ liệu giá & tín hiệu' },
  'loader.predict.step3': { en: 'Reading fresh headlines', vi: 'Đọc tin mới nhất' },
  'loader.predict.step4': { en: 'Writing the read', vi: 'Viết nhận định' },
  'loader.predict.log1': { en: 'fetch daily bars · 6mo', vi: 'tải nến ngày · 6 tháng' },
  'loader.predict.log2': { en: 'range low/high computed', vi: 'tính đỉnh/đáy khoảng' },
  'loader.predict.log3': { en: 'trend: short vs long MA', vi: 'xu hướng: MA ngắn/dài' },
  'loader.predict.log4': { en: 'scanning swing lows', vi: 'quét đáy dao động' },
  'loader.predict.log5': { en: 'support levels ranked', vi: 'xếp hạng vùng hỗ trợ' },
  'loader.predict.log6': { en: 'pulling fresh headlines', vi: 'tải tin mới nhất' },
  'loader.predict.log7': { en: 'strategy lens applied', vi: 'áp dụng chiến lược' },
  'loader.predict.log8': { en: 'validating AI output', vi: 'kiểm tra kết quả AI' },

  // briefing schedule editor
  'brief.enabled': { en: 'Scheduled briefings', vi: 'Bản tin theo lịch' },
  'brief.enabledHint': {
    en: 'Turn off to stop all automatic briefings. On-demand reports still work.',
    vi: 'Tắt để dừng mọi bản tin tự động. Bản tin theo yêu cầu vẫn hoạt động.',
  },
  'brief.morning': { en: 'MORNING BRIEFING', vi: 'BẢN TIN SÁNG' },
  'brief.morningHint': {
    en: 'The full start-of-day briefing.',
    vi: 'Bản tin đầy đủ đầu ngày.',
  },
  'brief.every': { en: 'CHECK IN EVERY (HOURS)', vi: 'CẬP NHẬT MỖI (GIỜ)' },
  'brief.everyHint': {
    en: 'Short intraday updates between the morning briefing and the cut-off.',
    vi: 'Cập nhật ngắn trong ngày, giữa bản tin sáng và giờ kết thúc.',
  },
  'brief.until': { en: 'LAST CHECK-IN', vi: 'CẬP NHẬT CUỐI' },
  'brief.untilHint': {
    en: 'No intraday updates after this time.',
    vi: 'Không cập nhật trong ngày sau giờ này.',
  },
  'brief.wrap': { en: 'END-OF-DAY WRAP', vi: 'TỔNG KẾT CUỐI NGÀY' },
  'brief.wrapHint': { en: 'The closing recap.', vi: 'Bản tổng kết cuối ngày.' },
  'brief.timezone': { en: 'All times in {tz}.', vi: 'Giờ theo múi {tz}.' },
  'brief.errTime': {
    en: '{field} must be a time like 08:30.',
    vi: '{field} phải là giờ dạng 08:30.',
  },
  'brief.errEvery': {
    en: 'Check in every 1 to {max} hours.',
    vi: 'Cập nhật mỗi 1 đến {max} giờ.',
  },
  'brief.errUntilBefore': {
    en: 'The last check-in can’t come before the morning briefing.',
    vi: 'Cập nhật cuối không thể trước bản tin sáng.',
  },
  'brief.errWrapBefore': {
    en: 'The wrap-up can’t come before the morning briefing.',
    vi: 'Tổng kết không thể trước bản tin sáng.',
  },
  'brief.saveErr': { en: 'Couldn’t save the schedule.', vi: 'Không lưu được lịch.' },

  // prediction strategies
  'strat.kicker': { en: 'AI · HOW IT THINKS', vi: 'AI · CÁCH SUY LUẬN' },
  'strat.title': { en: 'Strategies', vi: 'Chiến lược' },
  'strat.intro': {
    en: 'A strategy is the lens the AI reasons through. It changes how the evidence is weighed — never the real numbers.',
    vi: 'Chiến lược là góc nhìn AI dùng để suy luận. Nó thay đổi cách cân nhắc dữ liệu — không bao giờ thay đổi các con số thực.',
  },
  'strat.builtin': { en: 'BUILT-IN', vi: 'MẶC ĐỊNH' },
  'strat.manage': { en: 'Manage strategies', vi: 'Quản lý chiến lược' },
  'strat.active': { en: 'ACTIVE', vi: 'ĐANG DÙNG' },
  'strat.use': { en: 'Use this', vi: 'Dùng cái này' },
  'strat.edit': { en: 'Edit', vi: 'Sửa' },
  'strat.add': { en: 'Write your own', vi: 'Viết chiến lược riêng' },
  'strat.newTitle': { en: 'New strategy', vi: 'Chiến lược mới' },
  'strat.editTitle': { en: 'Edit strategy', vi: 'Sửa chiến lược' },
  'strat.nameLabel': { en: 'NAME', vi: 'TÊN' },
  'strat.namePlaceholder': { en: 'e.g. Deep value', vi: 'vd Giá trị sâu' },
  'strat.bodyLabel': { en: 'HOW TO WEIGH THE EVIDENCE', vi: 'CÁCH CÂN NHẮC DỮ LIỆU' },
  'strat.bodyPlaceholder': {
    en: 'e.g. Favour quality names 20%+ off their high where the bad news looks temporary. Ignore short-term momentum.',
    vi: 'vd Ưu tiên cổ phiếu tốt giảm trên 20% từ đỉnh khi tin xấu chỉ là tạm thời. Bỏ qua đà ngắn hạn.',
  },
  'strat.bodyHint': {
    en: 'Write it as instructions to an analyst. The AI still uses the real price signals and can never change them.',
    vi: 'Hãy viết như đang hướng dẫn một chuyên viên phân tích. AI vẫn dùng tín hiệu giá thực và không thể thay đổi chúng.',
  },
  'strat.save': { en: 'Save', vi: 'Lưu' },
  'strat.removeTitle': { en: 'Remove {name}?', vi: 'Xoá {name}?' },
  'strat.removeBody': {
    en: 'Predictions already made with it keep their accuracy record.',
    vi: 'Các dự đoán đã tạo bằng chiến lược này vẫn giữ lịch sử độ chính xác.',
  },
  'strat.footnote': {
    en: 'Each prediction records the strategy that made it, so accuracy can be compared later.',
    vi: 'Mỗi dự đoán ghi lại chiến lược đã tạo ra nó, để so sánh độ chính xác về sau.',
  },
  'strat.loadErr': { en: 'Couldn’t load strategies.', vi: 'Không tải được chiến lược.' },
  'strat.saveErr': { en: 'Couldn’t save', vi: 'Không lưu được' },
  'strat.removeErr': { en: 'Couldn’t remove', vi: 'Không xoá được' },
  'strat.activateErr': { en: 'Couldn’t switch strategy', vi: 'Không đổi được chiến lược' },

  // earnings (Report section + Predict chip)
  'earn.section': { en: 'EARNINGS', vi: 'KẾT QUẢ KINH DOANH' },
  'earn.next': { en: 'NEXT REPORT', vi: 'BÁO CÁO TỚI' },
  'earn.noDate': { en: 'Date not confirmed', vi: 'Chưa có lịch' },
  'earn.nextLabel': { en: 'NEXT', vi: 'SẮP TỚI' },
  'earn.lastLabel': { en: 'LAST', vi: 'GẦN ĐÂY' },
  'earn.reportedLabel': { en: 'REPORTED', vi: 'ĐÃ CÔNG BỐ' },
  'earn.qEnded': { en: 'ended {d}', vi: 'kết thúc {d}' },
  'earn.estimated': { en: 'estimated', vi: 'dự kiến' },
  'earn.eps': { en: 'EPS', vi: 'EPS' },
  'earn.vs': { en: 'vs', vi: 'so với' },
  'earn.est': { en: 'est.', vi: 'dự báo' },
  'earn.beat': { en: 'BEAT', vi: 'VƯỢT' },
  'earn.miss': { en: 'MISS', vi: 'HỤT' },
  'earn.inline': { en: 'INLINE', vi: 'ĐÚNG DỰ BÁO' },
  'earn.today': { en: 'today', vi: 'hôm nay' },
  'earn.tomorrow': { en: 'tomorrow', vi: 'ngày mai' },
  'earn.yesterday': { en: 'yesterday', vi: 'hôm qua' },
  'earn.inDays': { en: 'in {n} days', vi: 'sau {n} ngày' },
  'earn.daysAgo': { en: '{n} days ago', vi: '{n} ngày trước' },
  'earn.footnote': {
    en: 'LAST shows the fiscal quarter the EPS covers, not the day it was announced — results are published weeks after a quarter ends.',
    vi: 'GẦN ĐÂY là quý tài chính của số EPS, không phải ngày công bố — kết quả thường công bố vài tuần sau khi quý kết thúc.',
  },

  // entry evidence (Predict) — the working behind the entry advice
  'ev.riskReward': { en: 'RISK / REWARD', vi: 'RỦI RO / LỢI NHUẬN' },
  'ev.toSupport': { en: 'to nearest support', vi: 'đến hỗ trợ gần nhất' },
  'ev.toResistance': { en: 'to nearest resistance', vi: 'đến kháng cự gần nhất' },
  'ev.ratio': { en: 'REWARD : RISK', vi: 'LỢI NHUẬN : RỦI RO' },
  'ev.poorRatio': {
    en: 'risking more than the upside',
    vi: 'rủi ro lớn hơn lợi nhuận',
  },
  'ev.invalidation': {
    en: 'A close below {level} would break this read.',
    vi: 'Đóng cửa dưới {level} sẽ phá vỡ nhận định này.',
  },
  'ev.basedOn': { en: 'WHAT THIS IS BASED ON', vi: 'DỰA TRÊN ĐIỀU GÌ' },
  'ev.range.cheap': { en: 'Lower third of its range', vi: 'Vùng 1/3 dưới của khoảng giá' },
  'ev.range.fair': { en: 'Middle of its range', vi: 'Vùng giữa của khoảng giá' },
  'ev.range.rich': { en: 'Upper third of its range', vi: 'Vùng 1/3 trên của khoảng giá' },
  'ev.trend.up': { en: 'Trend is up', vi: 'Xu hướng tăng' },
  'ev.trend.down': { en: 'Trend is down', vi: 'Xu hướng giảm' },
  'ev.trend.sideways': { en: 'Trend is flat', vi: 'Xu hướng đi ngang' },
  'ev.thinHistory': {
    en: 'Not enough price history to judge the range',
    vi: 'Chưa đủ lịch sử giá để đánh giá khoảng',
  },
  'ev.aboveSupport': { en: '{pct}% above nearest support', vi: 'Cao hơn hỗ trợ gần nhất {pct}%' },
  'ev.earningsIn': { en: 'Earnings in {n} days', vi: 'Báo cáo sau {n} ngày' },
  'ev.headlines': { en: '{n} fresh headlines read', vi: 'Đã đọc {n} tin mới' },
  'ev.noHeadlines': { en: 'No fresh headlines found', vi: 'Không tìm thấy tin mới' },
  'ev.confidence': { en: 'CONFIDENCE', vi: 'ĐỘ TIN CẬY' },
  'ev.allAgree': {
    en: 'All {n} horizons agree ({lean})',
    vi: 'Cả {n} khung thời gian đồng thuận ({lean})',
  },
  'ev.someAgree': {
    en: '{n} of {total} horizons agree ({lean})',
    vi: '{n}/{total} khung thời gian đồng thuận ({lean})',
  },
  'ev.conflict': {
    en: 'Value and momentum disagree',
    vi: 'Định giá và đà giá trái chiều',
  },
  'ev.risks': { en: 'WHAT COULD MAKE THIS WRONG', vi: 'ĐIỀU GÌ CÓ THỂ LÀM SAI' },

  // second opinion (Predict) — an independent read by the other model
  'second.title': { en: 'SECOND OPINION · {model}', vi: 'Ý KIẾN THỨ HAI · {model}' },
  'second.agrees': {
    en: '✓ Agrees with the read above.',
    vi: '✓ Đồng thuận với nhận định ở trên.',
  },
  'second.disagrees': {
    en: '✕ Disagrees — the setup is ambiguous, treat it with more caution.',
    vi: '✕ Không đồng thuận — thiết lập chưa rõ ràng, hãy thận trọng hơn.',
  },
  'second.pending': {
    en: 'Asking {model} for a second opinion…',
    vi: 'Đang hỏi {model} ý kiến thứ hai…',
  },
  // Which model(s) run. `both` is the default: it is the only mode that produces
  // paired samples for the accuracy comparison.
  'predict.modeLabel': { en: 'ANALYST', vi: 'MÔ HÌNH' },
  'predict.mode.openai': { en: 'OPENAI', vi: 'OPENAI' },
  'predict.mode.deepseek': { en: 'DEEPSEEK', vi: 'DEEPSEEK' },
  'predict.mode.both': { en: 'BOTH', vi: 'CẢ HAI' },
  'predict.mode.downgraded': {
    en: 'You picked {asked}, but only {used} is set up on the server.',
    vi: 'Bạn chọn {asked}, nhưng máy chủ chỉ có {used}.',
  },
  // Three-way agreement (backend §11). "Partial" is the common case and used to
  // be shown as outright disagreement, which overstated it.
  'second.strong': {
    en: '✓ Agrees with the read above.',
    vi: '✓ Đồng thuận với nhận định ở trên.',
  },
  'second.partial': {
    en: '≈ Broadly agrees — same direction, different emphasis.',
    vi: '≈ Cơ bản đồng thuận — cùng hướng, khác mức độ nhấn mạnh.',
  },
  'second.conflict': {
    en: '✕ Genuinely conflicts — the setup is ambiguous, treat it with more caution.',
    vi: '✕ Thực sự trái chiều — thiết lập chưa rõ ràng, hãy thận trọng hơn.',
  },
  // What specifically differs. Codes must match app/prediction/agreement.py.
  'second.entry-differs': {
    en: 'Entry call differs: {primary} vs {second}',
    vi: 'Đánh giá điểm vào khác nhau: {primary} và {second}',
  },
  'second.direction-opposed': {
    en: 'Opposite direction at {horizon}: {primary} vs {second}',
    vi: 'Trái chiều ở {horizon}: {primary} và {second}',
  },
  'second.confidence-gap': {
    en: 'Far apart on how sure they are',
    vi: 'Chênh lệch lớn về mức độ chắc chắn',
  },
  'eval.byProvider': { en: 'ACCURACY BY MODEL', vi: 'ĐỘ CHÍNH XÁC THEO MÔ HÌNH' },
  'eval.providerNote': {
    en: 'Both models read the same evidence, so this compares the models themselves.',
    vi: 'Cả hai mô hình đọc cùng dữ liệu, nên đây là so sánh giữa các mô hình.',
  },

  // deterministic risk rules (Predict) — codes must match app/prediction/rules.py
  'rules.title': { en: 'RISK RULES APPLIED', vi: 'QUY TẮC RỦI RO ĐÃ ÁP DỤNG' },
  'rules.titleChecks': { en: 'RISK CHECKS', vi: 'KIỂM TRA RỦI RO' },
  'rules.downgraded': {
    en: 'StockPulse lowered the AI’s call from {from} to {to}:',
    vi: 'StockPulse hạ nhận định của AI từ {from} xuống {to}:',
  },
  'rules.confirmed': {
    en: 'The risk rules independently agree with {verdict}:',
    vi: 'Quy tắc rủi ro độc lập cũng cho kết quả {verdict}:',
  },
  'rules.weak-reward-risk': {
    en: 'Reward:risk of {ratio} is below the {minimum} minimum.',
    vi: 'Tỷ lệ lợi nhuận/rủi ro {ratio} thấp hơn mức tối thiểu {minimum}.',
  },
  'rules.earnings-imminent': {
    en: 'Earnings in {days} days will move this more than the setup does.',
    vi: 'Báo cáo sau {days} ngày sẽ tác động mạnh hơn cả thiết lập kỹ thuật.',
  },
  'rules.extreme-volatility': {
    en: 'Volatility is extreme for this stock — price levels are unreliable.',
    vi: 'Biến động cực lớn — các vùng giá không đáng tin cậy.',
  },
  'rules.high-volatility': {
    en: 'Volatility is high for this stock, so levels are looser than usual.',
    vi: 'Biến động cao hơn bình thường, các vùng giá kém chắc chắn.',
  },
  'rules.chasing': {
    en: 'Price is {atrs} average days above the nearest support — the good entry has gone.',
    vi: 'Giá đã cao hơn hỗ trợ gần nhất {atrs} phiên trung bình — điểm vào đẹp đã qua.',
  },
  'rules.stop-too-tight': {
    en: 'Invalidation is only {atrs} of an average day away — normal movement would hit it.',
    vi: 'Mức phá vỡ chỉ cách {atrs} phiên trung bình — biến động thường ngày sẽ chạm tới.',
  },
  'rules.invalid-stop': {
    en: 'The invalidation level sits above the current price.',
    vi: 'Mức phá vỡ nằm trên giá hiện tại.',
  },
  'rules.missing-data': {
    en: 'Not enough price history to judge this setup.',
    vi: 'Chưa đủ lịch sử giá để đánh giá thiết lập này.',
  },

  // watchlist quick-picker (Report + Predict)
  'picker.label': { en: 'FROM YOUR WATCHLIST', vi: 'TỪ DANH MỤC CỦA BẠN' },
  'picker.less': { en: 'Less', vi: 'Thu gọn' },

  // predict
  'predict.kicker': { en: 'AI · FORWARD-LOOKING', vi: 'AI · DỰ BÁO' },
  'predict.title': { en: 'Predict', vi: 'Dự đoán' },
  'predict.go': { en: 'Predict', vi: 'Dự đoán' },
  'predict.placeholder': { en: 'Ticker or company, e.g. WDC', vi: 'Mã hoặc tên, vd WDC' },
  'predict.genErr': { en: 'Couldn’t generate a read.', vi: 'Không tạo được nhận định.' },
  'predict.emptyTitle': { en: 'Forward-looking read', vi: 'Dự đoán xu hướng' },
  'predict.emptyBody': {
    en: 'Enter a stock and the AI gives a 1-week / 1-month / 3-month lean, grounded in real price signals + news. Speculative — not investment advice.',
    vi: 'Nhập một mã, AI đưa ra xu hướng 1 tuần / 1 tháng / 3 tháng dựa trên tín hiệu giá thực + tin tức. Chỉ tham khảo — không phải lời khuyên đầu tư.',
  },
  'predict.headline': { en: 'AI READ · NEXT 1–3 MONTHS', vi: 'AI ĐÁNH GIÁ · 1–3 THÁNG TỚI' },
  'predict.entryQ': { en: 'IS THIS A GOOD ENTRY?', vi: 'ĐÂY CÓ PHẢI GIÁ TỐT ĐỂ MUA?' },
  'predict.support': { en: 'SUPPORT', vi: 'HỖ TRỢ' },
  'predict.supportNear': { en: 'near', vi: 'gần' },
  'predict.supportLong': { en: 'long-term', vi: 'dài hạn' },
  'predict.price': { en: 'PRICE', vi: 'GIÁ' },
  'predict.chartHint': {
    en: 'Drag across the chart to read any point',
    vi: 'Kéo trên biểu đồ để xem từng điểm',
  },
  'predict.volume': { en: 'VOLUME', vi: 'KHỐI LƯỢNG' },
  'predict.trend': { en: 'TREND', vi: 'XU HƯỚNG' },
  'predict.drivers': { en: 'DRIVERS', vi: 'YẾU TỐ CHÍNH' },
  'predict.howReads': { en: 'How this reads the stock', vi: 'Cách AI đọc cổ phiếu' },
  'predict.strategy': { en: 'STRATEGY', vi: 'CHIẾN LƯỢC' },
  'predict.strategyNote': {
    en: 'This framework shapes how the AI weighs the evidence. The real numbers (price, discount, trend) are computed from market data — the strategy never changes them.',
    vi: 'Khung này định hướng cách AI cân nhắc dữ liệu. Các con số thực (giá, chiết khấu, xu hướng) được tính từ dữ liệu thị trường — chiến lược không thay đổi chúng.',
  },
  // lean / entry / confidence badges (keys mirror the API's enum values)
  'predict.lean.bounce': { en: 'BOUNCE', vi: 'TĂNG' },
  'predict.lean.dip': { en: 'DIP', vi: 'GIẢM' },
  'predict.lean.hold': { en: 'HOLD', vi: 'ĐI NGANG' },
  'predict.entry.good': { en: 'GOOD ENTRY', vi: 'GIÁ TỐT' },
  'predict.entry.fair': { en: 'FAIR', vi: 'TẠM ỔN' },
  'predict.entry.wait': { en: 'WAIT', vi: 'NÊN CHỜ' },
  'predict.conf.low': { en: 'low', vi: 'thấp' },
  'predict.conf.medium': { en: 'med', vi: 'TB' },
  'predict.conf.high': { en: 'high', vi: 'cao' },

  // evaluation
  'eval.title': { en: 'AI accuracy', vi: 'Độ chính xác AI' },
  'eval.headline': { en: 'DIRECTIONAL ACCURACY', vi: 'ĐỘ CHÍNH XÁC HƯỚNG' },
  'eval.ofCalls': { en: 'of {n} calls\nscored against real moves', vi: 'trên {n} nhận định\nso với biến động thực' },
  'eval.pending': { en: 'PENDING', vi: 'CHỜ' },
  'eval.bullish': { en: '▲ BULLISH', vi: '▲ TĂNG' },
  'eval.bearish': { en: '▼ BEARISH', vi: '▼ GIẢM' },
  'eval.byStrategy': { en: 'ACCURACY BY STRATEGY', vi: 'ĐỘ CHÍNH XÁC THEO CHIẾN LƯỢC' },
  'eval.calls': { en: '{n} scored', vi: '{n} đã chấm' },
  'eval.maturing': { en: '{n} maturing', vi: '{n} đang chờ' },
  'eval.thinSample': { en: 'Too few to judge', vi: 'Chưa đủ để kết luận' },
  'eval.strategyNote': {
    en: 'A strategy needs about {n} scored calls before its percentage means much. Predictions are scored once their horizon passes.',
    vi: 'Một chiến lược cần khoảng {n} nhận định đã chấm thì tỷ lệ mới có ý nghĩa. Dự đoán được chấm sau khi hết khung thời gian.',
  },
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

  // position exit advisor — "I already own this: hold, trim or sell?"
  // The pair reads as the two questions you can ask about one stock. "SELL?" is
  // the question, not the answer — the verdict below it is just as often HOLD.
  'exit.tab.buy': { en: 'BUY?', vi: 'MUA?' },
  'exit.tab.own': { en: 'SELL?', vi: 'BÁN?' },
  'exit.shares': { en: 'Shares', vi: 'Số cổ' },
  'exit.avgCost': { en: 'Avg cost', vi: 'Giá vốn' },
  'exit.go': { en: 'Analyse', vi: 'Phân tích' },
  'exit.emptyTitle': { en: 'Hold, trim or sell?', vi: 'Giữ, bán bớt hay bán hết?' },
  'exit.emptyBody': {
    en: 'Enter a ticker you own, how many shares and what you paid. StockPulse works out what holding is worth from today’s price.',
    vi: 'Nhập mã bạn đang giữ, số cổ và giá vốn. StockPulse sẽ tính xem việc tiếp tục giữ đáng giá bao nhiêu tính từ giá hôm nay.',
  },
  // Prefixed, because a bare "20" in a numeric field reads as a value that
  // is already there rather than as an example of what to type.
  'exit.sharesHint': { en: 'e.g. 20', vi: 'vd. 20' },
  'exit.costHint': { en: 'e.g. 420.00', vi: 'vd. 420.00' },
  'exit.needShares': { en: 'How many shares?', vi: 'Bao nhiêu cổ?' },
  'exit.needCost': { en: 'What did you pay?', vi: 'Giá vốn bao nhiêu?' },
  'exit.savedTitle': { en: 'YOUR POSITIONS', vi: 'VỊ THẾ CỦA BẠN' },
  'exit.savedHint': {
    en: 'TAP TO ANALYSE · LONG-PRESS TO REMOVE',
    vi: 'CHẠM ĐỂ PHÂN TÍCH · GIỮ ĐỂ XOÁ',
  },
  'exit.removeTitle': { en: 'Remove {ticker}?', vi: 'Xoá {ticker}?' },
  'exit.save': { en: 'Save this position', vi: 'Lưu vị thế này' },
  'exit.saveErr': { en: 'Couldn’t save that.', vi: 'Không lưu được.' },
  'exit.remove': { en: 'Remove', vi: 'Xoá' },

  'exit.verdict': { en: 'WHAT TO DO', vi: 'NÊN LÀM GÌ' },
  'exit.overridden': {
    en: 'The AI said “{ai}”. The risk rules below moved it.',
    vi: 'AI nói “{ai}”. Các quy tắc rủi ro bên dưới đã điều chỉnh lại.',
  },
  'exit.position': { en: 'YOUR POSITION', vi: 'VỊ THẾ CỦA BẠN' },
  'exit.costBasis': { en: 'Cost basis', vi: 'Vốn bỏ ra' },
  'exit.value': { en: 'Value now', vi: 'Giá trị hiện tại' },
  'exit.pnl': { en: 'Unrealised P&L', vi: 'Lãi/lỗ chưa chốt' },

  'exit.holdVsSell': { en: 'HOLD VS SELL', vi: 'GIỮ HAY BÁN' },
  'exit.lockNow': { en: 'Lock in now', vi: 'Chốt ngay bây giờ' },
  'exit.upsideTo': { en: 'If it runs to {level}', vi: 'Nếu lên tới {level}' },
  'exit.givebackTo': { en: 'If it falls to {level}', vi: 'Nếu rơi về {level}' },
  'exit.rr': { en: 'Reward vs risk from here', vi: 'Lợi/rủi ro tính từ đây' },
  'exit.rr.strong': { en: 'STRONG', vi: 'MẠNH' },
  'exit.rr.attractive': { en: 'ATTRACTIVE', vi: 'HẤP DẪN' },
  'exit.rr.balanced': { en: 'BALANCED', vi: 'CÂN BẰNG' },
  'exit.rr.weak': { en: 'WEAK', vi: 'YẾU' },
  'exit.rr.poor': { en: 'POOR', vi: 'KÉM' },
  'exit.noRr': {
    en: 'No clear level above or below, so there is no meaningful ratio to quote.',
    vi: 'Không có mốc rõ ràng ở trên hoặc dưới, nên không có tỷ lệ nào đáng nêu.',
  },
  'exit.noisySupport': {
    en: 'Careful: that floor is only {atrs} ATR away — inside one ordinary day’s move, so the ratio above flatters the trade.',
    vi: 'Lưu ý: mốc đó chỉ cách {atrs} ATR — nằm trong biên độ một ngày bình thường, nên tỷ lệ ở trên đang đẹp hơn thực tế.',
  },
  'exit.yourTarget': {
    en: 'Against your own target {level}: {profit} more, {ratio} to 1.',
    vi: 'So với mục tiêu của bạn {level}: thêm {profit}, tỷ lệ {ratio}.',
  },

  'exit.giveback': { en: 'IF IT FALLS', vi: 'NẾU GIÁ RƠI' },
  'exit.keeps': { en: 'you still keep {amount}', vi: 'bạn vẫn giữ được {amount}' },
  'exit.wouldLose': { en: 'you would be at {amount}', vi: 'bạn sẽ ở mức {amount}' },

  'exit.partial': { en: 'IF YOU TRIM', vi: 'NẾU BÁN BỚT' },
  'exit.shares.n': { en: '{n} shares', vi: '{n} cổ' },
  'exit.partialHint': {
    en: 'Proceeds and realised P&L are approximate — real tax lots may differ.',
    vi: 'Tiền thu về và lãi đã chốt chỉ là ước tính — lô thuế thực tế có thể khác.',
  },

  'exit.scenarios': { en: 'SCENARIOS', vi: 'CÁC KỊCH BẢN' },
  'exit.scenario.bull': { en: 'BULL', vi: 'TỐT' },
  'exit.scenario.base': { en: 'BASE', vi: 'CƠ SỞ' },
  'exit.scenario.bear': { en: 'BEAR', vi: 'XẤU' },
  'exit.fromHere': { en: 'From here:', vi: 'Tính từ đây:' },

  'exit.plans': { en: 'THREE WAYS TO PLAY IT', vi: 'BA CÁCH XỬ LÝ' },
  'exit.plan.conservative': { en: 'CONSERVATIVE', vi: 'THẬN TRỌNG' },
  'exit.plan.balanced': { en: 'BALANCED', vi: 'CÂN BẰNG' },
  'exit.plan.aggressive': { en: 'AGGRESSIVE', vi: 'MẠO HIỂM' },
  'exit.sellPct': { en: 'Sell {pct}%', vi: 'Bán {pct}%' },
  'exit.holdAll': { en: 'Hold it all', vi: 'Giữ toàn bộ' },
  'exit.stop': { en: 'Stop', vi: 'Cắt lỗ' },
  'exit.target': { en: 'Target', vi: 'Mục tiêu' },
  'exit.invalidation': { en: 'Thesis breaks', vi: 'Mất lý do giữ' },

  'exit.history': { en: 'HOW THIS CHANGED', vi: 'ĐÃ THAY ĐỔI RA SAO' },
  'exit.historyNote': {
    en: 'PAST VERDICTS ON THIS HOLDING · NOT A SCORE',
    vi: 'CÁC NHẬN ĐỊNH TRƯỚC VỀ VỊ THẾ NÀY · KHÔNG PHẢI ĐIỂM SỐ',
  },
  // Jargon, explained on tap. Every entry has TWO parts: what the number is,
  // and what it actually does to the advice — the second is the part you can't
  // get from a search engine, because it's specific to these rules.
  'exit.term.kicker': { en: 'WHAT THIS MEANS', vi: 'ĐIỀU NÀY NGHĨA LÀ GÌ' },
  'exit.stance.supports-hold': { en: 'ARGUES FOR HOLDING', vi: 'ỦNG HỘ VIỆC GIỮ' },
  'exit.stance.neutral': { en: 'NEITHER WAY', vi: 'KHÔNG NGHIÊNG BÊN NÀO' },
  'exit.stance.supports-trim': { en: 'ARGUES FOR TRIMMING', vi: 'ỦNG HỘ VIỆC BÁN BỚT' },
  'exit.termHint': { en: 'TAP ANY CHIP TO SEE WHAT IT MEANS', vi: 'CHẠM VÀO Ô BẤT KỲ ĐỂ XEM GIẢI THÍCH' },

  'term.trend.title': { en: 'Trend', vi: 'Xu hướng' },
  'term.trend.body': {
    en: 'Where the recent average price sits against the longer one. Up means the last two weeks have been stronger than the last six; down is the reverse; sideways means neither, within a small flat band.',
    vi: 'Giá trung bình gần đây so với trung bình dài hơn. "Up" nghĩa là hai tuần qua mạnh hơn sáu tuần qua; "down" thì ngược lại; "sideways" là không nghiêng hẳn về bên nào.',
  },
  'term.trend.effect': {
    en: 'A downtrend is one of five signals counted together — when three or more agree, the rules push toward trimming.',
    vi: 'Xu hướng giảm là một trong năm tín hiệu được đếm cùng nhau — từ ba tín hiệu trở lên, quy tắc sẽ nghiêng về bán bớt.',
  },

  'term.rsi.title': { en: 'RSI', vi: 'RSI' },
  'term.rsi.body': {
    en: 'Relative Strength Index, 0 to 100. It measures how one-sided recent moves have been. Above 70, buyers have dominated; below 30, sellers have.',
    vi: 'Chỉ số Sức mạnh Tương đối, từ 0 đến 100, đo mức độ một chiều của các phiên gần đây. Trên 70 là bên mua áp đảo; dưới 30 là bên bán áp đảo.',
  },
  'term.rsi.effect': {
    en: 'A high RSI is never a sell signal on its own — a strong stock can hold above 70 for weeks. It only counts here when the price is also right under a ceiling.',
    vi: 'RSI cao KHÔNG phải tín hiệu bán — một cổ phiếu mạnh có thể ở trên 70 hàng tuần liền. Nó chỉ được tính khi giá đồng thời áp sát vùng kháng cự.',
  },

  'term.atr.title': { en: 'ATR', vi: 'ATR' },
  'term.atr.body': {
    en: 'Average True Range — how much this stock typically moves in one day, in dollars. Measuring distances in ATRs is why the same 2% move is calm for one stock and dramatic for another.',
    vi: 'Biên độ dao động trung bình — mỗi ngày cổ phiếu này thường đi bao nhiêu đô la. Đo khoảng cách bằng ATR là lý do một cú 2% có thể là bình thường với mã này nhưng dữ dội với mã khác.',
  },
  'term.atr.effect': {
    en: 'Two ATR or more above the 20-day average counts as extended, which biases toward taking some profit. It is also how support is judged: closer than half an ATR is inside daily noise, further than three is too far to lean on.',
    vi: 'Từ 2 ATR trở lên so với trung bình 20 ngày được coi là căng, và nghiêng về chốt bớt lời. Nó cũng dùng để đánh giá mốc đỡ: gần hơn 0,5 ATR là nằm trong nhiễu hằng ngày, xa hơn 3 ATR thì quá xa để dựa vào.',
  },

  'term.relvol.title': { en: 'Relative volume', vi: 'Khối lượng tương đối' },
  'term.relvol.body': {
    en: 'Today’s trading volume against its 20-day average. 1.0x is an ordinary day; 2.0x is twice the usual participation.',
    vi: 'Khối lượng giao dịch hôm nay so với trung bình 20 ngày. 1,0x là một ngày bình thường; 2,0x là gấp đôi mức thường thấy.',
  },
  'term.relvol.effect': {
    en: 'It decides whether a breakout is believed. Price through a ceiling on ordinary volume is drift; 1.3x or more is what counts as confirmation, and only then does the app stop treating an extended price as a reason to trim.',
    vi: 'Nó quyết định một cú bứt phá có đáng tin không. Vượt kháng cự với khối lượng bình thường chỉ là trôi giá; từ 1,3x trở lên mới được coi là xác nhận, và chỉ khi đó ứng dụng mới ngừng coi giá căng là lý do bán bớt.',
  },

  'term.earnings.title': { en: 'Earnings date', vi: 'Ngày báo cáo' },
  'term.earnings.body': {
    en: 'Days until the company reports its quarterly results — the one scheduled moment when a stock can gap well beyond its usual daily range, in either direction.',
    vi: 'Số ngày còn lại đến khi công ty công bố kết quả quý — thời điểm duy nhất được báo trước mà giá có thể nhảy vọt vượt xa biên độ thường ngày, theo cả hai hướng.',
  },
  'term.earnings.effect': {
    en: 'Inside three days, holding everything becomes an active choice to take event risk, so the rules require a defined stop. It is not a sell signal: holding through a report is legitimate, as long as it is deliberate.',
    vi: 'Trong vòng ba ngày, giữ nguyên toàn bộ trở thành lựa chọn chủ động chấp nhận rủi ro sự kiện, nên quy tắc yêu cầu phải có mức cắt lỗ rõ ràng. Đây không phải tín hiệu bán: giữ qua báo cáo là hợp lệ, miễn là có chủ đích.',
  },

  'term.market.title': { en: 'Market backdrop', vi: 'Bối cảnh thị trường' },
  'term.market.body': {
    en: 'The S&P 500 trend, the VIX (the market’s expected volatility for the month ahead: under 15 calm, 20+ elevated, 30+ stressed), and how far this stock has run against the index over 20 sessions, in percentage points.',
    vi: 'Xu hướng S&P 500, chỉ số VIX (mức biến động thị trường dự kiến cho tháng tới: dưới 15 là bình lặng, trên 20 là cao, trên 30 là căng thẳng), và mức chênh lệch của cổ phiếu này so với chỉ số trong 20 phiên, tính bằng điểm phần trăm.',
  },
  'term.market.effect': {
    en: 'It answers whether a move was the stock or the tide. Lagging the market is one of the five deterioration signals, and a hostile market stops a breakout from counting as confirmed.',
    vi: 'Nó trả lời câu hỏi: cú chạy này là của cổ phiếu hay của cả thị trường? Tụt lại sau thị trường là một trong năm tín hiệu suy yếu, và thị trường bất lợi khiến một cú bứt phá không được tính là đã xác nhận.',
  },

  'term.rr.title': { en: 'Reward vs risk', vi: 'Lợi nhuận so với rủi ro' },
  'term.rr.body': {
    en: 'The room above divided by the room below, measured from today’s price: distance to the next ceiling against distance to the nearest floor. 2.0 means twice as much room up as down.',
    vi: 'Khoảng trống phía trên chia cho khoảng trống phía dưới, tính từ giá hôm nay: khoảng cách tới mốc cản gần nhất so với khoảng cách tới mốc đỡ gần nhất. 2,0 nghĩa là dư địa tăng gấp đôi dư địa giảm.',
  },
  'term.rr.effect': {
    en: 'Deliberately measured from today, not from what you paid — what you paid does not change how much room is left. Below 1.0 the rules bias toward trimming. Always read it next to how far the floor is: a ratio built on a floor half an ATR away flatters the trade.',
    vi: 'Cố ý tính từ hôm nay, không tính từ giá vốn của bạn — giá vốn không làm thay đổi dư địa còn lại. Dưới 1,0 thì quy tắc nghiêng về bán bớt. Luôn đọc nó cùng với khoảng cách tới mốc đỡ: một tỷ lệ dựa trên mốc đỡ chỉ cách nửa ATR là đang đẹp hơn thực tế.',
  },

  'exit.why': { en: 'WHY', vi: 'VÌ SAO' },
  'exit.context': { en: 'CONTEXT', vi: 'BỐI CẢNH' },
  'exit.vsSma20': { en: '{atrs} ATR vs 20D', vi: '{atrs} ATR so với 20N' },
  'exit.relVol': { en: 'VOL {x}×', vi: 'KL {x}×' },
  'exit.earningsIn': { en: 'EARNINGS IN {days}D', vi: 'BCTC SAU {days}N' },
  'exit.market': { en: 'Market {trend} · VIX {vix} ({regime})', vi: 'Thị trường {trend} · VIX {vix} ({regime})' },
  'exit.vsMarket': { en: '{pts} pts vs market (20D)', vi: '{pts} điểm so với thị trường (20N)' },
  'exit.refresh': {
    en: 'The quote is stale while the market is open — refresh before acting on this.',
    vi: 'Giá đang cũ trong lúc thị trường mở cửa — hãy làm mới trước khi hành động.',
  },

  // exposure ladder (spec §3.3)
  'exit.action.hold': { en: 'HOLD', vi: 'GIỮ' },
  'exit.action.hold-with-stop': { en: 'HOLD WITH A STOP', vi: 'GIỮ, CÓ CẮT LỖ' },
  'exit.action.partial-sell': { en: 'SELL SOME', vi: 'BÁN BỚT' },
  'exit.action.take-profit': { en: 'TAKE PROFIT', vi: 'CHỐT LỜI' },
  'exit.action.reduce': { en: 'REDUCE', vi: 'GIẢM MẠNH' },
  'exit.action.exit': { en: 'EXIT', vi: 'BÁN HẾT' },
  'exit.action.sell-into-strength': { en: 'SELL INTO STRENGTH', vi: 'BÁN KHI ĐANG MẠNH' },
  'exit.action.wait-for-confirmation': { en: 'WAIT', vi: 'CHỜ XÁC NHẬN' },
  'exit.action.no-clear-edge': { en: 'NO CLEAR EDGE', vi: 'CHƯA RÕ LỢI THẾ' },

  // deterministic rule findings (codes + numbers from the backend)
  'exit.rule.stale-quote': {
    en: 'The last price is {minutes} minutes old.',
    vi: 'Giá cuối cùng đã cũ {minutes} phút.',
  },
  'exit.rule.invalid-stop': {
    en: 'Your stop at {stop} is not below the price — it would trigger immediately.',
    vi: 'Mức cắt lỗ {stop} không nằm dưới giá — sẽ khớp ngay lập tức.',
  },
  'exit.rule.earnings-imminent': {
    en: 'Earnings in {days} days: holding it all is choosing to take event risk.',
    vi: 'Còn {days} ngày tới báo cáo: giữ nguyên là chấp nhận rủi ro sự kiện.',
  },
  'exit.rule.weak-hold-reward-risk': {
    en: 'Only {ratio} to 1 left from here (below {minimum}) — trimming is the percentage play.',
    vi: 'Chỉ còn tỷ lệ {ratio} tính từ đây (dưới {minimum}) — bán bớt là lựa chọn hợp lý hơn.',
  },
  'exit.rule.support-broken': {
    en: 'Price is below every recent floor — there is nothing near to lean on.',
    vi: 'Giá đã xuống dưới mọi đáy gần đây — không còn mốc đỡ nào ở gần.',
  },
  'exit.rule.trend-deterioration': {
    en: 'The trend that justified holding is coming apart.',
    vi: 'Xu hướng từng là lý do để giữ đang xấu đi.',
  },
  'exit.rule.extended': {
    en: 'Stretched well above its average — some profit-taking is the percentage play.',
    vi: 'Đang căng khá xa so với đường trung bình — chốt bớt là lựa chọn hợp lý.',
  },
  'exit.rule.valid-breakout': {
    en: 'Extended, but this is a real breakout on confirming volume — not a reason to sell on its own.',
    vi: 'Có căng, nhưng đây là cú bứt phá thật với khối lượng xác nhận — chưa phải lý do để bán.',
  },
  'exit.rule.below-cost': {
    en: 'You are below your average cost, so none of this is profit-taking.',
    vi: 'Bạn đang dưới giá vốn, nên đây không phải là chốt lời.',
  },
  'exit.rule.support-far': {
    en: 'The nearest floor is {atrs} ATR below — the price has run well clear of it, so there is nothing near to lean on.',
    vi: 'Mốc đỡ gần nhất cách tới {atrs} ATR — giá đã chạy quá xa khỏi nó, nên không còn mốc nào ở gần để dựa vào.',
  },
  'exit.rule.support-inside-noise': {
    en: 'The nearest floor is only {atrs} ATR away — inside a normal day’s move.',
    vi: 'Mốc đỡ gần nhất chỉ cách {atrs} ATR — nằm trong biên độ một ngày bình thường.',
  },

  // loader (exit)
  'loader.exit.kicker': { en: 'ANALYSING EXIT ENTRY', vi: 'PHÂN TÍCH ENTRY BÁN' },
  // The big scrambling word. Kept SHORT on purpose: it renders at 34px with
  // numberOfLines={1}, so anything longer than ~10 characters is clipped.
  // The full phrase lives in the kicker above it.
  'loader.exit.scramble': { en: 'ANALYSING', vi: 'PHÂN TÍCH' },
  'loader.exit.headline': { en: 'YOUR POSITION', vi: 'VỊ THẾ CỦA BẠN' },
  'loader.exit.step1': { en: 'Finding the stock', vi: 'Tìm cổ phiếu' },
  'loader.exit.step2': { en: 'Pricing the position', vi: 'Định giá vị thế' },
  'loader.exit.step3': { en: 'Reading the news', vi: 'Đọc tin tức' },
  'loader.exit.step4': { en: 'Checking the market', vi: 'Kiểm tra thị trường' },
  'loader.exit.step5': { en: 'Weighing hold vs sell', vi: 'Cân giữ hay bán' },
};
