from port_common import *

NAV_A_ACTIVE = 'class="flex flex-col items-center justify-center min-w-[64px] min-h-[44px] gap-0.5 transition-colors text-on-surface font-semibold [&amp;_span.material-symbols-outlined]:text-primary [&amp;_.active-indicator]:bg-primary [&amp;_.active-indicator]:w-1.5 [&amp;_.active-indicator]:h-1.5"'
NAV_A = 'class="flex flex-col items-center justify-center min-w-[64px] min-h-[44px] gap-0.5 text-on-surface-variant hover:text-on-surface transition-colors"'

def nav(v, active):
    # Stitch nav: every page marks one tab active; href="#" -> real routes
    v.s = v.s.replace('aria-current="page" ', '')
    v.s = v.s.replace(NAV_A_ACTIVE, NAV_A)
    for p in ("home", "timeline", "status"):
        old = f'{NAV_A} data-path="{p}" href="#"'
        assert v.s.count(old) == 1, (v.name, p)
        cls = NAV_A_ACTIVE if p == active else NAV_A
        cur = 'aria-current="page" ' if p == active else ''
        v.s = v.s.replace(old, f'{cur}{cls} data-path="{p}" href="#{p}"')

# ======================= HOME
v = View("home")
v.r('<button class="w-11 h-11 flex items-center justify-center rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface transition-colors"><span class="material-symbols-outlined text-[20px]">notifications</span></button>',
    '<button class="w-11 h-11 flex items-center justify-center rounded-full bg-surface-container-low text-on-surface-variant hover:text-on-surface transition-colors" aria-label="알림" data-bell><span class="material-symbols-outlined text-[20px]">notifications</span></button>')
v.r(AVATAR, AVATAR_LINK)
v.r('<span class="">보리</span>\n<span class="ml-1 text-[13px]">🐾</span>', '<span class="" data-k="pet_name">보리</span>\n<span class="ml-1 text-[13px]">🐾</span>')
v.r('<button aria-label="카메라 설정" class="', '<a href="#status" aria-label="카메라 설정" class="')
v.r('<span class="material-symbols-outlined text-[20px]">tune</span>\n</button>', '<span class="material-symbols-outlined text-[20px]">tune</span>\n</a>')
v.r('<button aria-label="이전 날짜" class="', '<button aria-label="이전 날짜" data-day="-1" class="')
v.r('<span class="font-headline-sm text-headline-sm text-on-surface font-semibold">10월 26일 (목)</span>\n<span class="w-1.5 h-1.5 rounded-full bg-primary"></span>',
    '<span class="font-headline-sm text-headline-sm text-on-surface font-semibold" data-k="date_label">10월 26일 (목)</span>\n<span class="w-1.5 h-1.5 rounded-full bg-primary" data-show="is_today"></span>')
v.r('<span class="font-label-sm text-label-sm text-on-surface-variant mt-0.5">케어 주기: 12:00 ~ 익일 12:00</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant mt-0.5">케어 주기: <span data-k="care_cycle">12:00 ~ 익일 12:00</span></span>')
v.r('<button aria-label="다음 날짜" class="w-11 h-11 flex items-center justify-center rounded-full text-on-surface-variant opacity-40 cursor-not-allowed" disabled="">',
    '<button aria-label="다음 날짜" data-day="1" class="w-11 h-11 flex items-center justify-center rounded-full text-on-surface-variant disabled:opacity-40 disabled:cursor-not-allowed hover:text-on-surface hover:bg-surface-container-high transition-colors">')
v.r('<img alt="보리의 2층 케이지 실시간 야간 캠 캡처" class="w-full h-full object-cover select-none" src="">', '<img alt="케이지 최신 스냅샷" class="w-full h-full object-cover select-none" data-img="snapshot" src="">')
v.r('''<span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
<span class="font-label-md text-label-md text-primary font-semibold">정상 스트리밍 중</span>
<span class="material-symbols-outlined text-primary text-[14px] ml-0.5">wifi</span>''', '''<span class="w-2 h-2 rounded-full animate-pulse" data-cls="cam_dot"></span>
<span class="font-label-md text-label-md font-semibold" data-cls="cam_text" data-k="cam_label">정상 스트리밍 중</span>
<span class="material-symbols-outlined text-[14px] ml-0.5" data-cls="cam_text" data-k="cam_icon">wifi</span>''')
v.r('<span class="material-symbols-outlined text-tertiary text-[15px]">bedtime</span>\n<span class="font-label-sm text-label-sm text-on-surface">야간 적외선 모드</span>',
    '<span class="material-symbols-outlined text-tertiary text-[15px]" data-k="daypart_icon">bedtime</span>\n<span class="font-label-sm text-label-sm text-on-surface" data-k="daypart">야간 적외선 모드</span>')
v.r('''<span class="flex items-center text-primary font-medium">
<span class="material-symbols-outlined text-[14px] mr-1">motion_sensor_active</span>
            실시간 감지 ON
          </span>
<span class="text-outline-variant">•</span>
<span class="">HD 1080p</span>''', '''<span class="flex items-center text-primary font-medium">
<span class="material-symbols-outlined text-[14px] mr-1">motion_sensor_active</span>
            <span data-k="detect">실시간 감지 ON</span>
          </span>
<span class="text-outline-variant">•</span>
<span class="" data-k="snap_age">HD 1080p</span>''')
v.r('<button aria-label="전체화면 확대" class="', '<a href="/media/latest.jpg" target="_blank" aria-label="전체화면 확대" class="')
v.r('<span class="material-symbols-outlined text-[20px]">fullscreen</span>\n</button>', '<span class="material-symbols-outlined text-[20px]">fullscreen</span>\n</a>')
# mode chips -> camera_status indicator
CH_ON = 'shrink-0 px-3 py-1.5 rounded-full bg-primary-container/20 text-primary font-label-sm text-label-sm font-semibold flex items-center space-x-1'
CH_OFF = 'shrink-0 px-3 py-1.5 rounded-full bg-surface-container-high text-on-surface-variant hover:text-on-surface font-label-sm text-label-sm transition-colors'
v.r(f'<button class="{CH_ON}">\n<span class="w-1.5 h-1.5 rounded-full bg-primary"></span>\n<span class="">정상 작동</span>', f'<button class="{CH_ON}" data-mode="online">\n<span class="w-1.5 h-1.5 rounded-full bg-primary"></span>\n<span class="">정상 작동</span>')
v.r(f'<button class="{CH_OFF}">\n<span class="">프라이버시</span>', f'<button class="{CH_OFF}" data-mode="privacy">\n<span class="w-1.5 h-1.5 rounded-full bg-primary hidden"></span>\n<span class="">프라이버시</span>')
v.r(f'<button class="{CH_OFF}">\n<span class="">화면 어두움</span>', f'<button class="{CH_OFF}" data-mode="dark">\n<span class="w-1.5 h-1.5 rounded-full bg-primary hidden"></span>\n<span class="">화면 어두움</span>')
v.r(f'<button class="{CH_OFF}">\n<span class="">지연 2분</span>', f'<button class="{CH_OFF}" data-mode="offline">\n<span class="w-1.5 h-1.5 rounded-full bg-primary hidden"></span>\n<span class="" data-k="lag_label">지연 2분</span>')
v.r('<span class="font-headline-sm text-headline-sm text-on-surface font-semibold tracking-tight">03:14에 물 마시는 중이에요</span>\n<span class="inline-flex px-1.5 py-0.5 rounded text-[10px] bg-tertiary-container/30 text-tertiary font-medium">실시간 포착</span>',
    '<span class="font-headline-sm text-headline-sm text-on-surface font-semibold tracking-tight truncate min-w-0" data-k="moment_title">움직임 확인 중</span>\n<span class="inline-flex shrink-0 whitespace-nowrap px-1.5 py-0.5 rounded text-[10px] bg-tertiary-container/30 text-tertiary font-medium" data-k="moment_tag">실시간 포착</span>')
v.r('''        쳇바퀴를 8분간 달린 후 급수기(PIP 볼)로 이동했어요. 수분 섭취가 규칙적으로 유지되고 있습니다.''', '''        <span data-k="moment_text">움직임이 감지되면 여기에서 요약해 드릴게요.</span>''')
v.r('<span class="font-headline-md text-headline-md text-on-surface font-bold">17</span>', '<span class="font-headline-md text-headline-md text-on-surface font-bold" data-k="active_min">17</span>')
v.r('''<div class="flex items-center space-x-0.5 mt-1 text-primary">
<span class="material-symbols-outlined text-[12px]">arrow_upward</span>
<span class="font-label-sm text-label-sm font-medium">+4분 (어제)</span>''', '''<div class="flex items-center space-x-0.5 mt-1 text-primary" data-cls="delta_cls">
<span class="material-symbols-outlined text-[12px]" data-k="delta_icon">arrow_upward</span>
<span class="font-label-sm text-label-sm font-medium" data-k="delta">+4분 (어제)</span>''')
v.r('<span class="font-headline-md text-headline-md text-on-surface font-bold">4</span>', '<span class="font-headline-md text-headline-md text-on-surface font-bold" data-k="sessions">4</span>')
v.r('<span class="material-symbols-outlined text-[12px]">sync</span>\n<span class="font-label-sm text-label-sm">쳇바퀴 3회</span>', '<span class="material-symbols-outlined text-[12px]">sync</span>\n<span class="font-label-sm text-label-sm" data-k="clips">쳇바퀴 3회</span>')
v.r('<span class="font-headline-md text-headline-md text-on-surface font-bold truncate">6,005</span>', '<span class="font-headline-md text-headline-md text-on-surface font-bold truncate" data-k="distance">6,005</span>')
v.r('<span class="">활동 보통</span>', '<span class="" data-k="level">활동 보통</span>')
v.r('<span class="font-label-lg text-label-lg text-on-surface font-semibold">평소 대비 +20% 활발해요</span>\n<span class="text-[13px]">🌿</span>', '<span class="font-label-lg text-label-lg text-on-surface font-semibold" data-k="cmp_title">평소 대비 +20% 활발해요</span>\n<span class="text-[13px]">🌿</span>')
v.r('''        지난 7일 평균 활동량(14분)보다 생기 넘치는 밤을 보내고 있어요.''', '''        <span data-k="cmp_text">지난 7일 평균 활동량(14분)보다 생기 넘치는 밤을 보내고 있어요.</span>''')
v.r('<span class="font-label-sm text-label-sm text-on-surface-variant mt-0.5">정오(12:00)부터 익일 정오(12:00) 기준 집계</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant mt-0.5" data-k="chart_sub">정오(12:00)부터 익일 정오(12:00) 기준 집계</span>')
v.r('<div class="absolute top-0 left-[62%] -translate-x-1/2 flex flex-col items-center pointer-events-none">', '<div class="absolute top-0 left-[62%] -translate-x-1/2 flex flex-col items-center pointer-events-none" id="now-bubble">')
v.r('<span class="">지금 03:14 (8분)</span>', '<span class="" data-k="bubble">지금 03:14 (8분)</span>')
v.rx(r'(<div class="relative z-10 w-full h-32 flex items-end justify-between px-1")>.*?</div>\s*(<!-- X-Axis Labels -->)', r'\1 id="bars"></div>\n\2')
v.r('''<span class="">12시</span>
<span class="">15시</span>''', '''<span class="" data-k="ax0">12시</span>
<span class="" data-k="ax1">15시</span>''')
v.r('''<span class="">18시</span>
<span class="">21시</span>
<span class="text-tertiary font-semibold">00시</span>
<span class="text-primary font-bold">03시</span>
<span class="">06시</span>
<span class="">09시</span>
<span class="">12시</span>''', '''<span class="" data-k="ax2">18시</span>
<span class="" data-k="ax3">21시</span>
<span class="text-tertiary font-semibold" data-k="ax4">00시</span>
<span class="text-primary font-bold" data-k="ax5">03시</span>
<span class="" data-k="ax6">06시</span>
<span class="" data-k="ax7">09시</span>
<span class="" data-k="ax8">12시</span>''')
v.r('<span class="font-label-sm text-label-sm text-primary font-semibold">현재 활동 (03:14)</span>', '<span class="font-label-sm text-label-sm text-primary font-semibold" data-k="legend_now">현재 활동 (03:14)</span>')
v.r('<div class="font-label-lg text-label-lg text-on-surface font-semibold">급수기 잔량 85%</div>\n<div class="font-body-sm text-body-sm text-on-surface-variant">오늘 3회 정상 음수 완료</div>',
    '')
v.r('''<button class="px-3 py-2 rounded-full bg-surface-container-high hover:bg-surface-bright text-on-surface font-label-md text-label-md transition-colors min-h-[44px] flex items-center">
      기록 보기
    </button>''', '''<a href="#timeline" class="hs-action shrink-0 px-3 py-2 rounded-full bg-surface-container-high hover:bg-surface-bright text-on-surface font-label-md text-label-md transition-colors min-h-[44px] flex items-center">기록 보기</a>''')
nav(v, "home")
v.save()

# ======================= TIMELINE
v = View("timeline")
v.r(AVATAR, AVATAR_LINK)
v.r('<button aria-label="이전 날짜" class="', '<button aria-label="이전 날짜" data-day="-1" class="')
v.r('<span class="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight">오늘 (10.26 목)</span>\n<span class="inline-flex items-center px-2 py-0.5 rounded-full text-label-sm font-label-sm bg-primary/10 text-primary">기록 중</span>',
    '<span class="font-headline-md text-headline-md text-on-surface font-semibold tracking-tight" data-k="date_label">오늘 (10.26 목)</span>\n<span class="inline-flex items-center px-2 py-0.5 rounded-full text-label-sm font-label-sm bg-primary/10 text-primary" data-show="is_today">기록 중</span>')
v.r('<span class="font-label-sm text-label-sm text-on-surface-variant">야행성 주기: 12:00 ~ 익일 12:00</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant">야행성 주기: <span data-k="care_cycle">12:00 ~ 익일 12:00</span></span>')
v.r('<button aria-label="달력 선택" class="w-11 h-11 flex items-center justify-center rounded-full bg-surface-container text-on-surface-variant hover:text-on-surface transition-colors">\n<span class="material-symbols-outlined text-[20px]">calendar_today</span>\n</button>',
    '<label aria-label="달력 선택" class="relative w-11 h-11 flex items-center justify-center rounded-full bg-surface-container text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer">\n<span class="material-symbols-outlined text-[20px]">calendar_today</span>\n<input type="date" id="date-pick" class="absolute inset-0 opacity-0 cursor-pointer"/>\n</label>')
v.r('<span class="px-1.5 py-0.2 bg-on-primary/20 rounded-full text-[10px]">4건</span>', '<span class="px-1.5 py-0.2 bg-on-primary/20 rounded-full text-[10px]"><span data-k="count">4</span>건</span>')
for f in ("wheel", "water", "tunnel"):
    v.r(f'transition-all" data-filter="{f}">', f'transition-all disabled:opacity-50" data-filter="{f}" disabled title="행동 분류는 준비 중이에요">')
v.r('<span class="font-body-sm text-body-sm text-on-surface">현재 골든햄스터 <strong>모찌</strong>는 아늑하게 수면 중이에요 💤</span>', '<span class="font-body-sm text-body-sm text-on-surface" data-html="live_line">기록을 불러오는 중이에요</span>')
v.r('<span class="font-label-sm text-label-sm text-on-surface-variant">22.4°C / 48%</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant" data-k="live_meta">22.4°C / 48%</span>')
# Session cards: keep Stitch "Session 1" card as the template, drop the demo ones
a = v.s.index('<!-- Session 1'); b = v.s.index('<!-- Session 2'); c = v.s.index('<!-- Bottom Interactive Floating Controller -->')
card = v.s[a:b]
end_feed = v.s.rindex('</div>', b, c)
v.s = v.s[:a] + card + '<div class="hidden p-space-lg rounded-[20px] bg-surface-container text-center font-body-sm text-body-sm text-on-surface-variant relative z-10" id="empty">이 날은 기록된 활동이 없어요. 🌙</div>\n' + v.s[end_feed:]
v.r('<article class="timeline-card relative z-10', '<article data-tpl="session" class="timeline-card relative z-10')
v.r('<div class="w-8 h-8 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0">\n<span class="material-symbols-outlined text-[18px]">water_drop</span>',
    '<div class="w-8 h-8 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0">\n<span class="material-symbols-outlined text-[18px]" data-k="icon">water_drop</span>')
v.r('<h3 class="font-headline-sm text-headline-sm text-on-surface tracking-tight">새벽 간식 &amp; 물 마시기</h3>', '<h3 class="font-headline-sm text-headline-sm text-on-surface tracking-tight" data-k="title">활동</h3>')
v.r('<span class="font-label-sm text-label-sm text-primary font-medium">03:12 ~ 03:18 (6분간 활동)</span>', '<span class="font-label-sm text-label-sm text-primary font-medium" data-k="range">03:12 ~ 03:18 (6분간 활동)</span>')
v.r('<span class="px-2 py-0.5 rounded-full text-label-sm font-label-sm bg-surface-container-high text-on-surface-variant">클립 3개</span>', '<span class="px-2 py-0.5 rounded-full text-label-sm font-label-sm bg-surface-container-high text-on-surface-variant">클립 <span data-k="nclips">3</span>개</span>')
v.r('''<span class="material-symbols-outlined text-[14px]">route</span>
          이동 거리 1,840 px''', '''<span class="material-symbols-outlined text-[14px]">route</span>
          이동 거리 <span data-k="dist">1,840</span> px''')
v.r('''<span class="material-symbols-outlined text-[14px]">timer</span>
          물 섭취 120초''', '''<span class="material-symbols-outlined text-[14px]">timer</span>
          움직임 <span data-k="frames">120</span>프레임''')
v.r('''        물그릇에서 2분 동안 물을 시원하게 마신 뒤, 쳇바퀴 뒤편 모래 목욕존으로 가볍게 탐색 이동했어요.''', '''        <span data-k="memo">움직임이 감지되면 여기에 요약이 보여요.</span>''')
cs = v.s.index('<!-- Clip 1 -->'); ce = v.s.index('<!-- Clip 2 -->'); ge = v.s.index('</div>\n</div>\n</article>')
clip = v.s[cs:ce]
clip = clip.replace('<div aria-label="03:12 녹화 클립 재생" class="group', '<a data-tpl="clip" aria-label="녹화 클립 재생" class="group').replace('role="button" tabindex="0">', 'href="#">', 1)
clip = clip.replace('<img class="w-full h-full object-cover" src="">', '<img class="w-full h-full object-cover" loading="lazy" data-img="thumb" src="">')
clip = clip.replace('font-mono">03:12</span>\n</div>', 'font-mono" data-k="t">03:12</span>\n</a>')
v.s = v.s[:cs] + clip + v.s[ge:]
v.r('<span class="font-label-md text-label-md text-on-surface font-medium">실시간 스트리밍 대기 중</span>', '<span class="font-label-md text-label-md text-on-surface font-medium" data-k="float_label">더 이상 이벤트가 없습니다</span>')
v.r('<span class="w-2 h-2 rounded-full bg-primary animate-pulse"></span>\n<span class="font-label-md', '<span class="w-2 h-2 rounded-full animate-pulse" data-cls="cam_dot"></span>\n<span class="font-label-md')
v.r('active:scale-95 transition-all" href="#">\n<span class="material-symbols-outlined text-[18px]">videocam</span>', 'active:scale-95 transition-all" href="/media/latest.jpg" target="_blank">\n<span class="material-symbols-outlined text-[18px]">videocam</span>')
nav(v, "timeline")
v.save()

# ======================= SESSION DETAIL
v = View("session")
v.r(AVATAR, AVATAR_LINK)
v.s = v.s.replace('onclick="history.back()"', 'data-back')
v.r('<span class="font-headline-sm text-headline-sm text-on-surface">이벤트 클립 #03</span>', '<span class="font-headline-sm text-headline-sm text-on-surface">이벤트 클립 #<span data-k="idx">03</span></span>')
v.r('''<button class="w-11 h-11 flex items-center justify-center rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface transition-colors">
<span class="material-symbols-outlined text-[20px]">share</span>''', '''<button id="btn-share" class="w-11 h-11 flex items-center justify-center rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface transition-colors">
<span class="material-symbols-outlined text-[20px]">share</span>''')
v.r('''<button class="w-11 h-11 flex items-center justify-center rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface transition-colors">
<span class="material-symbols-outlined text-[20px]">more_vert</span>''', '''<button disabled aria-label="더보기 (준비 중)" class="w-11 h-11 flex items-center justify-center rounded-full bg-surface-container hover:bg-surface-container-high text-on-surface transition-colors">
<span class="material-symbols-outlined text-[20px]">more_vert</span>''')
v.r('<img alt="야간 적외선 모니터링 클립" class="w-full h-full object-cover brightness-95 contrast-105" src="">', '<video class="w-full h-full object-cover brightness-95 contrast-105" id="vid" playsinline muted preload="metadata"></video>')
v.r('<path d="M 120,135 Q 165,110 205,150 T 245,160" fill="none" filter="url(#glow)" opacity="0.85" stroke="#5af0b3" stroke-dasharray="4 4" stroke-width="2.5"></path>', '<path id="trail" d="" fill="none" filter="url(#glow)" opacity="0.85" stroke="#5af0b3" stroke-dasharray="4 4" stroke-width="2.5"></path>')
v.r('<circle cx="120" cy="135" fill="#34d399" opacity="0.6" r="3.5"></circle>\n<circle cx="180" cy="128" fill="#34d399" opacity="0.6" r="3.5"></circle>', '<circle id="trail-a" cx="-10" cy="-10" fill="#34d399" opacity="0.6" r="3.5"></circle>\n<circle id="trail-b" cx="-10" cy="-10" fill="#34d399" opacity="0.6" r="3.5"></circle>')
v.r('<circle cx="245" cy="160" fill="#5af0b3" filter="url(#glow)" r="5">', '<circle id="trail-end" cx="-10" cy="-10" fill="#5af0b3" filter="url(#glow)" r="5">')
v.r('<span class="text-label-sm font-label-sm text-secondary">2023.10.26 03:14:58 AM</span>', '<span class="text-label-sm font-label-sm text-secondary" data-k="rec_time">2023.10.26 03:14:58 AM</span>')
v.r('<span class="material-symbols-outlined text-[14px] text-primary">maps_auto</span>', '<span class="material-symbols-outlined text-[14px] text-primary" data-k="cam_icon">nightlight</span>')
v.r('<span class="text-label-sm font-label-sm text-primary font-medium">IR NIGHT CAM</span>', '<span class="text-label-sm font-label-sm text-primary font-medium" data-k="cam_mode">IR NIGHT CAM</span>')
v.r('<div class="absolute top-[46%] left-[51%] transform -translate-x-1/2 pointer-events-none flex flex-col items-center">', '<div class="absolute top-[46%] left-[51%] transform -translate-x-1/2 pointer-events-none flex flex-col items-center" id="tag">')
v.r('<span class="text-label-sm font-label-sm text-primary font-semibold">보리 감지 (신뢰도 98%)</span>', '<span class="text-label-sm font-label-sm text-primary font-semibold" data-k="tag">보리 감지 (신뢰도 98%)</span>')
v.r('<div class="relative w-full h-2 mb-2 bg-surface-container-highest/60 rounded-full cursor-pointer flex items-center">\n<div class="h-full bg-primary rounded-full relative" style="width: 46%;">',
    '<div class="relative w-full h-2 mb-2 bg-surface-container-highest/60 rounded-full cursor-pointer flex items-center" id="scrub">\n<div class="h-full bg-primary rounded-full relative" id="progress" style="width: 0%;">')
v.r('<div class="absolute left-[38%] top-0 bottom-0 w-1 bg-tertiary-container rounded-full" title="수분 섭취 시점"></div>', '<div class="absolute left-[38%] top-0 bottom-0 w-1 bg-tertiary-container rounded-full" id="peak-pin" title="최대 움직임 시점"></div>')
v.r('<span class="material-symbols-outlined text-[20px]" id="playIcon">pause</span>', '<span class="material-symbols-outlined text-[20px]" id="playIcon">play_arrow</span>')
v.r('<span class="text-on-surface font-semibold">00:42</span>\n<span class="text-secondary/70"> / 01:30</span>', '<span class="text-on-surface font-semibold" id="cur">00:00</span>\n<span class="text-secondary/70"> / <span id="dur">00:00</span></span>')
v.r('''            FHD
          </span>''', '''            <span id="quality">SD</span>
          </span>''')
v.r('''<button class="w-8 h-8 flex items-center justify-center rounded-full bg-surface-container/70 hover:bg-surface-container text-on-surface transition-colors">
<span class="material-symbols-outlined text-[18px]">fullscreen</span>''', '''<button id="fsBtn" class="w-8 h-8 flex items-center justify-center rounded-full bg-surface-container/70 hover:bg-surface-container text-on-surface transition-colors">
<span class="material-symbols-outlined text-[18px]">fullscreen</span>''')
v.r('<span class="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm">야간 적외선</span>', '<span class="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm" data-k="daypart">야간 적외선</span>')
v.r('<h2 class="font-headline-md text-headline-md text-on-surface tracking-tight">새벽 수분 섭취 및 모래 구역 탐색</h2>', '<h2 class="font-headline-md text-headline-md text-on-surface tracking-tight" data-k="title">새벽 수분 섭취 및 모래 구역 탐색</h2>')
v.r('id="favBtn">', 'id="favBtn" title="즐겨찾기">')
v.r('<span class="">03:14:10</span>', '<span class="" data-k="start">03:14:10</span>')
v.r('<span class="">1분 30초</span>', '<span class="" data-k="duration">1분 30초</span>')
v.r('<span class="">1,240 <span class="font-label-sm text-label-sm font-normal text-secondary">px</span></span>', '<span class=""><span data-k="dist">1,240</span> <span class="font-label-sm text-label-sm font-normal text-secondary">px</span></span>')
v.r('<span class="font-label-sm text-label-sm text-secondary">심박 추정 (안정)</span>', '<span class="font-label-sm text-label-sm text-secondary">움직임 프레임</span>')
v.r('<span class="material-symbols-outlined text-[18px] text-error">favorite</span>\n<span class="">342 <span class="font-label-sm text-label-sm font-normal text-secondary">bpm</span></span>',
    '<span class="material-symbols-outlined text-[18px] text-error">motion_photos_on</span>\n<span class=""><span data-k="frames">342</span> <span class="font-label-sm text-label-sm font-normal text-secondary">프레임</span></span>')
v.r('<span class="text-secondary">주요 감지 행동 분석</span>\n<span class="text-on-surface font-semibold">물 마시기 (80%) · 서성거리기 (20%)</span>', '<span class="text-secondary">움직임 비율 (행동 분류 준비 중)</span>\n<span class="text-on-surface font-semibold" data-k="ratio_label">움직임 · 정지</span>')
v.r('<div class="h-full bg-primary transition-all duration-500" style="width: 80%;" title="물 마시기 80%"></div>\n<div class="h-full bg-tertiary-container transition-all duration-500" style="width: 20%;" title="서성거리기 20%"></div>',
    '<div class="h-full bg-primary transition-all duration-500" id="ratio-a" style="width: 0%;" title="움직임"></div>\n<div class="h-full bg-tertiary-container transition-all duration-500" id="ratio-b" style="width: 0%;" title="정지"></div>')
v.r('<span class="px-2 py-0.5 rounded-full bg-surface-container text-secondary text-label-sm font-label-sm">케이지 전경 평면도</span>', '<span class="px-2 py-0.5 rounded-full bg-surface-container text-secondary text-label-sm font-label-sm">카메라 화면 기준</span>')
v.r('<path d="M 60,50 C 90,50 130,80 175,75 S 250,90 275,115" fill="none" filter="url(#glow)" opacity="0.9" stroke="#5af0b3" stroke-dasharray="5 4" stroke-width="2.5"></path>', '<path id="map-trail" d="" fill="none" filter="url(#glow)" opacity="0.9" stroke="#5af0b3" stroke-dasharray="5 4" stroke-width="2.5"></path>')
v.r('<circle cx="60" cy="50" fill="#cbc6bd" r="4"></circle>\n<circle cx="175" cy="75" fill="#34d399" r="4"></circle>', '<circle id="map-a" cx="-10" cy="-10" fill="#cbc6bd" r="4"></circle>\n<circle id="map-b" cx="-10" cy="-10" fill="#34d399" r="4"></circle>')
v.r('<circle cx="275" cy="115" fill="#5af0b3" r="6"></circle>', '<circle id="map-end" cx="-10" cy="-10" fill="#5af0b3" r="6"></circle>')
v.r('''            은신처
          </div>''', '''            화면 좌측
          </div>''')
v.r('''            챗바퀴 구역
          </div>''', '''            중앙
          </div>''')
v.r('''            모래목욕존
          </div>''', '''            화면 우측
          </div>''')
v.r('''            물그릇 (현재 위치)''', '''            <span data-k="end_zone">마지막 위치</span>''')
v.r('<span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-secondary"></span> 시작: 은신처 입구</span>', '<span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-secondary"></span> 시작: <span data-k="start_zone">은신처 입구</span></span>')
v.r('<span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-primary"></span> 종료: 물그릇 세라믹 존</span>', '<span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-primary"></span> 종료: <span data-k="end_zone2">구역</span></span>')
v.r('<button class="py-space-md px-space-sm rounded-xl bg-surface-container-low hover:bg-surface-container text-on-surface transition-all flex items-center justify-between shadow-sm min-h-[48px]">\n<div class="flex items-center gap-1 text-label-md font-label-md">\n<span class="material-symbols-outlined text-[18px] text-secondary">chevron_left</span>',
    '<button id="btn-prev" class="py-space-md px-space-sm rounded-xl bg-surface-container-low hover:bg-surface-container text-on-surface transition-all flex items-center justify-between shadow-sm min-h-[48px] disabled:opacity-40">\n<div class="flex items-center gap-1 text-label-md font-label-md">\n<span class="material-symbols-outlined text-[18px] text-secondary">chevron_left</span>')
v.r('<span class="text-label-sm font-label-sm text-on-surface font-semibold">03:12 (챗바퀴)</span>', '<span class="text-label-sm font-label-sm text-on-surface font-semibold" data-k="prev">03:12 (챗바퀴)</span>')
v.r('<button class="py-space-md px-space-sm rounded-xl bg-surface-container-low hover:bg-surface-container text-on-surface transition-all flex items-center justify-between shadow-sm min-h-[48px]">\n<span class="text-label-sm font-label-sm text-on-surface font-semibold">03:17 (그루밍)</span>',
    '<button id="btn-next" class="py-space-md px-space-sm rounded-xl bg-surface-container-low hover:bg-surface-container text-on-surface transition-all flex items-center justify-between shadow-sm min-h-[48px] disabled:opacity-40">\n<span class="text-label-sm font-label-sm text-on-surface font-semibold" data-k="next">03:17 (그루밍)</span>')
v.r('<span id="downloadText" class="">클립 기기에 저장 (MP4, 18MB)</span>', '<span id="downloadText" class="" data-k="download">클립 기기에 저장 (MP4, 18MB)</span>')
v.r('<span class="material-symbols-outlined text-[18px] text-tertiary">star_outline</span>\n<span class="">즐겨찾기 보관함에 추가</span>', '<span class="material-symbols-outlined text-[18px] text-tertiary" id="favActionIcon">star_outline</span>\n<span class="" data-k="fav_label">즐겨찾기 보관함에 추가</span>')
v.save()

# ======================= STATUS
v = View("status")
v.r(AVATAR, AVATAR_LINK)
v.r('''<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 text-primary font-label-sm text-label-sm">
<span class="w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
        실시간 연결됨''', '''<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 font-label-sm text-label-sm" data-cls="cam_text">
<span class="w-1.5 h-1.5 rounded-full animate-pulse" data-cls="cam_dot"></span>
        <span data-k="cam_chip">실시간 연결됨</span>''')
v.r('<p class="font-body-sm text-body-sm text-on-surface-variant">HomeStudio 캠 Pro (케이지 내부 설치형)</p>', '<p class="font-body-sm text-body-sm text-on-surface-variant">TVS-W1000 (Uniview) · 스냅샷 수집 모드</p>')
v.r('<img class="w-full h-full object-cover" src="">', '<img class="w-full h-full object-cover" data-img="snapshot" src="">')
v.r('<span class="font-label-sm text-label-sm text-white drop-shadow">케이지 내부 03:14:58 AM</span>', '<span class="font-label-sm text-label-sm text-white drop-shadow">케이지 <span data-k="snap_time">03:14:58 AM</span></span>')
v.r('<span class="font-label-sm text-label-sm px-2 py-0.5 rounded bg-surface-container-lowest/70 text-on-surface backdrop-blur-sm">REC 1080p IR</span>', '<span class="font-label-sm text-label-sm px-2 py-0.5 rounded bg-surface-container-lowest/70 text-on-surface backdrop-blur-sm" data-k="rec_spec">REC 1080p IR</span>')
v.r('<div class="font-headline-sm text-headline-sm text-on-surface">정상 가동</div>\n<span class="font-label-sm text-label-sm text-primary">99.8% 가동률</span>', '<div class="font-headline-sm text-headline-sm text-on-surface" data-k="cam_state">정상 가동</div>\n<span class="font-label-sm text-label-sm text-primary" data-k="cam_state_sub">99.8% 가동률</span>')
v.r('<div class="font-headline-sm text-headline-sm text-on-surface">우수 (-48dBm)</div>\n<span class="font-label-sm text-label-sm text-on-surface-variant">5GHz 안정적</span>', '<div class="font-headline-sm text-headline-sm text-on-surface">측정 준비 중</div>\n<span class="font-label-sm text-label-sm text-on-surface-variant">유선 LAN 연결</span>')
v.r('<span class="font-label-sm text-label-sm text-on-surface-variant">5V 2A 무소음 공급</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant">어댑터 상시 연결</span>')
v.r('''          렌즈 온도
        </div>
<div class="font-headline-sm text-headline-sm text-on-surface">28.4°C</div>
<span class="font-label-sm text-label-sm text-primary">안전 적정온도</span>''', '''          렌즈 온도
        </div>
<div class="font-headline-sm text-headline-sm text-on-surface">–</div>
<span class="font-label-sm text-label-sm text-on-surface-variant">센서 미연결</span>''')
v.r('''        마지막 신호 수신: 3초 전''', '''        마지막 신호 수신: <span data-k="last_seen">3초 전</span>''')
v.r('<span class="text-primary font-medium">캠 펌웨어 v2.4.1</span>', '<span class="text-primary font-medium" data-k="fps">캠 펌웨어 v2.4.1</span>')
v.r('<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-surface-container-high text-on-surface-variant">차단 기능</span>', '<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-surface-container-high text-on-surface-variant" data-k="privacy_tag">차단 기능</span>')
v.r('''          집사가 방에 있거나 케이지를 청소할 때 렌즈 셔터를 닫고 스트리밍을 즉시 정지합니다.''', '''          집사가 방에 있거나 케이지를 청소할 때 렌즈를 수납하고 감지·저장을 멈춥니다. (관리자만 전환, 카메라 실제 상태 표시)''')
v.r('<button aria-label="프라이버시 모드 토글" class="shrink-0 w-12 h-7 rounded-full bg-surface-variant p-0.5 transition-colors duration-200 focus:outline-none" id="privacy-toggle" type="button">\n<div class="w-6 h-6 rounded-full bg-on-surface shadow-sm transform transition-transform duration-200" id="privacy-knob"></div>',
    '<button aria-label="프라이버시 모드 토글" class="shrink-0 w-12 h-7 rounded-full bg-surface-variant p-0.5 transition-colors duration-200 focus:outline-none disabled:opacity-50" id="privacy-toggle" type="button" data-admin>\n<div class="w-6 h-6 rounded-full bg-on-surface shadow-sm transform transition-transform duration-200" id="privacy-knob"></div>')
v.r('<span class="font-label-lg text-label-lg text-on-surface">나이트 비전<br>(940nm 불가시 IR)</span>\n<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary">눈부심 없음</span>',
    '<span class="font-label-lg text-label-lg text-on-surface">나이트 비전<br>(카메라 자동 IR)</span>\n<span class="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary">카메라 설정</span>')
v.r('''          반려동물 시야를 자극하지 않는 적외선 파장으로 빛이 전혀 없는 암흑에서도 선명히 감지합니다.''', '''          어두워지면 카메라가 적외선 모드로 자동 전환합니다. HomeStudio에서는 변경하지 않아요.''')
v.r('id="ir-toggle" type="button">', 'id="ir-toggle" type="button" disabled>')
v.r('<p class="font-label-sm text-label-sm text-on-surface-variant">클라우드 롤링 스토리지</p>', '<p class="font-label-sm text-label-sm text-on-surface-variant">집 PC 로컬 롤링 스토리지</p>')
v.r('<span class="font-label-md text-label-md text-primary font-semibold">21% 사용 중</span>', '<span class="font-label-md text-label-md text-primary font-semibold"><span data-k="pct">21</span>% 사용 중</span>')
v.r('<span class="text-on-surface font-semibold">3.2 GB <span class="font-normal text-on-surface-variant">/ 15.0 GB</span></span>\n<span class="text-on-surface-variant font-label-sm text-label-sm">잔여 11.8 GB</span>',
    '<span class="text-on-surface font-semibold"><span data-k="used">3.2 GB</span> <span class="font-normal text-on-surface-variant">/ <span data-k="cap">15.0 GB</span></span></span>\n<span class="text-on-surface-variant font-label-sm text-label-sm">디스크 여유 <span data-k="free">11.8 GB</span></span>')
v.r('<div class="h-full bg-primary rounded-full transition-all duration-500" style="width: 21%"></div>', '<div class="h-full bg-primary rounded-full transition-all duration-500" id="storage-bar" style="width: 0%"></div>')
v.r('''          AI 활동 하이라이트 영상''', '''          이벤트 클립·썸네일''')
v.r('<span class="font-label-md text-label-md text-on-surface font-medium">자동 롤링 보관 (최근 14일)</span>', '<span class="font-label-md text-label-md text-on-surface font-medium">자동 롤링 보관 (용량 한도)</span>')
v.r('''          14일이 지난 일반 이동 영상은 자동 정리되며, 사용자가 ‘보관함’에 저장한 순간 숏폼은 영구 보존됩니다.''', '''          한도에 가까워지면 오래된 클립부터 정리돼요. 영상은 외부 클라우드로 전송되지 않습니다.''')
v.r('''<button class="flex-1 min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors" type="button">''', '''<button class="flex-1 min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50" type="button" disabled title="준비 중">''')
v.r('''<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors" type="button">''', '''<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50" type="button" disabled title="준비 중">''')
v.r('''          낮 12:00 (정오)''', '''          <span data-k="care_start">낮 12:00 (정오)</span>''')
v.r('''        야행성 소동물의 활동 패턴에 맞춰 매일 낮 12:00부터 익일 낮 12:00까지의 챗바퀴·식사 데이터를 하루 단위로 묶어 종합 분석합니다.''', '''        야행성 소동물의 활동 패턴에 맞춰 매일 <span data-k="care_cycle">낮 12:00부터 익일 낮 12:00</span>까지의 활동 데이터를 하루 단위로 묶어 분석합니다.''')
v.r('''<button class="min-h-[44px] px-4 py-2 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg flex items-center gap-1 hover:opacity-90 transition-opacity" type="button">
<span class="">시간 변경하기</span>''', '''<button class="min-h-[44px] px-4 py-2 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg flex items-center gap-1 hover:opacity-90 transition-opacity disabled:opacity-40" type="button" id="btn-care" data-admin>
<span class="">시간 변경하기</span>''')
# device log: one template item, filled from real camera/event data
a = v.s.index('<!-- Item 1 -->'); b = v.s.index('<!-- Item 2 -->'); c = v.s.index('<!-- Reassurance Footnote -->')
item = v.s[a:b].replace('<div class="p-3 rounded-xl', '<div data-tpl="log" class="p-3 rounded-xl', 1)
item = item.replace('<span class="w-2 h-2 rounded-full bg-primary shrink-0"></span>', '<span class="w-2 h-2 rounded-full bg-primary shrink-0" data-cls="dot"></span>')
item = item.replace('<span class="font-body-sm text-body-sm text-on-surface font-medium">Wi-Fi 연결 정상 복구</span>', '<span class="font-body-sm text-body-sm text-on-surface font-medium" data-k="title"></span>')
item = item.replace('<span class="font-label-sm text-label-sm text-on-surface-variant">신호 대역 5GHz 재연결 완료</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant" data-k="sub"></span>')
item = item.replace('<span class="font-label-sm text-label-sm text-on-surface-variant shrink-0">오늘 03:00</span>', '<span class="font-label-sm text-label-sm text-on-surface-variant shrink-0" data-k="when"></span>')
end_list = v.s.rindex('</div>\n</div>', b, c)
v.s = v.s[:a] + item + v.s[end_list:]
v.r('''<button class="font-label-sm text-label-sm text-primary flex items-center gap-0.5 hover:underline" type="button">
        전체 보기''', '''<button class="font-label-sm text-label-sm text-primary flex items-center gap-0.5 hover:underline" type="button" onclick="location.hash='#timeline'">
        전체 보기''')
# account & family: no Stitch card for this -> reuse the care-day card component
acct = '''<!-- Account & Family (same card component as care-day) -->
<div class="rounded-[20px] bg-surface-container p-space-lg flex flex-col gap-space-md shadow-sm">
<div class="flex items-center gap-2">
<div class="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-primary">
<span class="material-symbols-outlined text-[18px]">group</span>
</div>
<div>
<h3 class="font-headline-sm text-headline-sm text-on-surface tracking-tight">계정 &amp; 가족 공유</h3>
<p class="font-label-sm text-label-sm text-on-surface-variant" data-k="me">-</p>
</div>
</div>
<div class="flex flex-col gap-2.5" id="members"><div data-tpl="member" class="p-3 rounded-xl bg-surface-container-low flex items-center justify-between">
<div class="flex items-center gap-3"><span class="w-2 h-2 rounded-full bg-primary shrink-0" data-cls="dot"></span><span class="font-body-sm text-body-sm text-on-surface font-medium" data-k="email"></span></div>
<span class="font-label-sm text-label-sm text-on-surface-variant shrink-0" data-k="role"></span></div></div>
<div class="hidden p-space-md rounded-xl bg-surface-container-low flex items-center justify-between" id="invite-box">
<span class="font-label-md text-label-md text-on-surface-variant">초대 코드 (7일, 1회용)</span>
<span class="font-headline-sm text-headline-sm text-primary tracking-widest font-mono" data-k="invite"></span>
</div>
<div class="flex items-center gap-space-sm">
<button class="flex-1 min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors" type="button" id="btn-invite" data-admin>
<span class="material-symbols-outlined text-[18px]">group_add</span>
        가족 초대 코드 만들기
      </button>
</div>
<div class="grid grid-cols-2 gap-space-sm">
<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors" type="button" id="btn-password">
<span class="material-symbols-outlined text-[18px]">password</span>
        비밀번호 변경
      </button>
<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors" type="button" id="btn-pinset">
<span class="material-symbols-outlined text-[18px]">dialpad</span>
        <span class="flex flex-col items-start leading-tight"><span data-k="pin_title">간편 PIN 설정</span><span class="font-label-sm font-normal text-on-surface-variant" data-k="pin_sub">이 기기 미등록</span></span>
      </button>
<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50" type="button" id="btn-petedit" data-admin>
<span class="material-symbols-outlined text-[18px]">pets</span>
        반려동물 정보
      </button>
<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors" type="button" id="btn-lock">
<span class="material-symbols-outlined text-[18px]">lock</span>
        이 기기 잠금
      </button>
<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50" type="button" id="btn-camfind" data-admin>
<span class="material-symbols-outlined text-[18px]">videocam</span>
        카메라 다시 찾기
      </button>
<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors" type="button" id="btn-zones">
<span class="material-symbols-outlined text-[18px]">pets</span>
        케이지 구역
      </button>
</div>
<div class="flex items-center gap-space-sm">
<button class="flex-1 min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors" type="button" id="btn-logout">
<span class="material-symbols-outlined text-[18px]">logout</span>
        로그아웃
      </button>
</div>
</div>
<!-- Reassurance Footnote -->'''
v.r('<!-- Reassurance Footnote -->', acct)
v.r('<span class="font-label-sm text-label-sm">HomeStudio 암호화 안심 스트리밍 가동 중</span>', '<span class="font-label-sm text-label-sm">HomeStudio 로컬 저장 · Tailscale 사설망 전용</span>')
nav(v, "status")
v.save()
print("main views ok")

# ======================= NOTIFICATIONS (no Stitch screen: status header/nav + its "최근 기기 로그" card components)
import re as _re
for _n in ("timeline", "status"):  # header bell -> notification center
    _p = f"/workspace/port/out/views/{_n}.html"
    _t = open(_p).read()
    _old = 'transition-colors"><span class="material-symbols-outlined text-[20px]">notifications</span>'
    assert _t.count(_old) == 1, _n
    open(_p, "w").write(_t.replace(_old, 'transition-colors" aria-label="알림" data-bell><span class="material-symbols-outlined text-[20px]">notifications</span>'))
_s = open("/workspace/port/out/views/status.html").read()
_head = _s[:_s.index("<main")] + _re.search(r"<main[^>]*>", _s).group(0)
_nav = _s[_s.index("</main>"):]
_body = '''<div class="flex flex-col gap-space-md pt-space-md pb-28">
<div class="rounded-[20px] bg-surface-container p-space-lg flex flex-col gap-space-md shadow-sm">
<div class="flex items-center justify-between">
<div class="flex items-center gap-2">
<div class="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-on-surface">
<span class="material-symbols-outlined text-[18px]">notifications</span>
</div>
<div>
<h3 class="font-headline-sm text-headline-sm text-on-surface tracking-tight">알림</h3>
<p class="font-label-sm text-label-sm text-on-surface-variant" data-k="sub">HomeStudio 앱 안에서만 보관돼요</p>
</div>
</div>
<button class="font-label-sm text-label-sm text-primary flex items-center gap-0.5 hover:underline whitespace-nowrap shrink-0" type="button" id="btn-read">
        모두 읽음
        <span class="material-symbols-outlined text-[14px]">check</span>
</button>
</div>
<div class="flex flex-col gap-2.5" id="noti-list">
<div data-tpl="noti" class="p-3 rounded-xl bg-surface-container-low flex items-start justify-between gap-3">
<div class="flex items-start gap-3">
<span class="w-2 h-2 mt-1.5 rounded-full shrink-0" data-cls="dot"></span>
<div class="flex flex-col gap-0.5">
<span class="font-body-sm text-body-sm text-on-surface font-medium" data-k="title"></span>
<span class="font-label-sm text-label-sm text-on-surface-variant leading-relaxed" data-k="body"></span>
</div>
</div>
<span class="font-label-sm text-label-sm text-on-surface-variant shrink-0" data-k="when"></span>
</div>
</div>
<p class="hidden font-body-sm text-body-sm text-on-surface-variant text-center py-space-md" id="noti-empty">아직 알림이 없어요.</p>
</div>
<div class="p-3 rounded-xl bg-surface-container flex items-center gap-3">
<span class="material-symbols-outlined text-[20px] text-tertiary">notifications_paused</span>
<p class="font-label-sm text-label-sm text-on-surface-variant leading-relaxed" data-k="quiet">수면 중 안심 알림 필터링</p>
</div>
</div>
'''
open("/workspace/port/out/views/notifications.html", "w").write(_head + _body + _nav)
print("notifications view ok")

# ---- zones editor (P4 prep): no Stitch screen exists -> composed only from existing Stitch components
#      (status header/nav, camera preview card, timeline filter chips, notification rows, status account buttons)
_zbody = '''<div class="flex flex-col gap-space-md pt-space-md pb-28">
<div class="rounded-[20px] bg-surface-container p-space-lg flex flex-col gap-space-md shadow-sm">
<div class="flex items-center justify-between">
<div class="flex items-center gap-2">
<div class="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center text-on-surface">
<span class="material-symbols-outlined text-[18px]">pets</span>
</div>
<div>
<h3 class="font-headline-sm text-headline-sm text-on-surface tracking-tight">케이지 구역</h3>
<p class="font-label-sm text-label-sm text-on-surface-variant" data-k="sub">사진 위를 눌러 구역 꼭짓점을 찍어요</p>
</div>
</div>
</div>
<div class="relative w-full aspect-video rounded-xl overflow-hidden bg-surface-container-lowest touch-none" id="zone-stage">
<img class="w-full h-full object-cover opacity-85" id="zone-img" src="" alt="최근 스냅샷"/>
<svg class="absolute inset-0 w-full h-full" id="zone-svg" viewBox="0 0 1 1" preserveAspectRatio="none"></svg>
<div class="absolute bottom-3 right-3 px-2 py-0.5 rounded-lg bg-surface-dim/70 backdrop-blur-sm text-label-sm font-label-sm text-on-surface-variant">
        <span data-k="hint">2점 = 사각형 · 3점 이상 = 다각형</span>
      </div>
</div>
<div class="flex items-center gap-2 overflow-x-auto py-1 no-scrollbar" id="zone-kinds">
<button class="filter-chip flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-primary text-on-primary font-label-md text-label-md shrink-0 shadow-sm transition-all" data-kind="wheel" type="button"><span>쳇바퀴</span></button>
<button class="filter-chip flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-surface-container-high text-on-surface-variant font-label-md text-label-md shrink-0 hover:text-on-surface transition-all" data-kind="food" type="button"><span>먹이 그릇</span></button>
<button class="filter-chip flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-surface-container-high text-on-surface-variant font-label-md text-label-md shrink-0 hover:text-on-surface transition-all" data-kind="water" type="button"><span>물병</span></button>
<button class="filter-chip flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-surface-container-high text-on-surface-variant font-label-md text-label-md shrink-0 hover:text-on-surface transition-all" data-kind="hide" type="button"><span>은신처</span></button>
<button class="filter-chip flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-surface-container-high text-on-surface-variant font-label-md text-label-md shrink-0 hover:text-on-surface transition-all" data-kind="custom" type="button"><span>직접 입력</span></button>
</div>
<div class="grid grid-cols-2 gap-space-sm">
<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50" type="button" id="btn-zclear" data-admin>
<span class="material-symbols-outlined text-[18px]">close</span>
        점 지우기
      </button>
<button class="min-h-[44px] px-space-md py-2.5 rounded-xl bg-surface-container-high hover:bg-surface-variant text-on-surface font-label-md text-label-md flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50" type="button" id="btn-zadd" data-admin>
<span class="material-symbols-outlined text-[18px]">add</span>
        구역 추가
      </button>
</div>
<div class="flex flex-col gap-2.5" id="zone-list">
<div data-tpl="zone" class="p-3 rounded-xl bg-surface-container-low flex items-start justify-between gap-3">
<div class="flex items-start gap-3">
<span class="w-2 h-2 mt-1.5 rounded-full shrink-0" data-cls="dot"></span>
<div class="flex flex-col gap-0.5">
<span class="font-body-sm text-body-sm text-on-surface font-medium" data-k="name"></span>
<span class="font-label-sm text-label-sm text-on-surface-variant leading-relaxed" data-k="stat"></span>
</div>
</div>
<button class="font-label-sm text-label-sm text-error flex items-center gap-0.5 hover:underline whitespace-nowrap shrink-0 disabled:opacity-50" type="button" data-del data-admin>
<span class="material-symbols-outlined text-[14px]">delete</span>삭제</button>
</div>
</div>
<p class="hidden font-body-sm text-body-sm text-on-surface-variant text-center py-space-md" id="zone-empty">아직 구역이 없어요.</p>
<button class="w-full h-14 rounded-2xl bg-primary text-on-primary font-label-lg text-label-lg flex items-center justify-center gap-2 shadow-sm active:scale-[0.98] transition-all disabled:opacity-50" type="button" id="btn-zsave" data-admin>
<span>구역 저장</span>
<span class="material-symbols-outlined text-[20px]">check</span>
</button>
</div>
</div>
'''
open("/workspace/port/out/views/zones.html", "w").write(_head + _zbody + _nav)
print("zones view ok")
