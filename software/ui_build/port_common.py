import re, json
RAW = "/workspace/port/raw/"
URLS = json.load(open("/workspace/port/urls.json"))
ASSET = {"img_25c08793.png": "assets/mascot.png", "img_5f5d3133.png": "assets/mascot.png",
         "img_4f9c6622.png": "assets/art-signup.jpg", "img_3f11b6e6.png": "assets/art-pet.jpg",
         "img_c3e4867c.png": "assets/art-schedule.jpg"}

class View:
    def __init__(self, name):
        s = open(RAW + name + ".html").read()
        s = re.sub(r"<script.*?</script>", "", s, flags=re.S)
        s = re.sub(r' data-alt="[^"]*"', '', s)
        def img(m):
            f = URLS[m.group(0)]
            return ASSET.get(f, "")  # demo photos -> empty src, filled by app.js
        s = re.sub(r'https://lh3\.googleusercontent\.com/[^"\')\s]+', img, s)
        s = s.replace("홈 스튜디오", "HomeStudio").replace("홈스튜디오", "HomeStudio")
        self.s, self.name = s, name

    def r(self, old, new, n=1):
        c = self.s.count(old)
        assert c == n, f"{self.name}: expected {n} got {c}: {old[:90]!r}"
        self.s = self.s.replace(old, new)
        return self

    def rx(self, pat, new, n=1):
        self.s, c = re.subn(pat, new, self.s, flags=re.S)
        assert c == n, f"{self.name}: regex {n} got {c}: {pat[:90]!r}"
        return self

    def save(self, name=None):
        assert "lh3.googleusercontent" not in self.s and "https://" not in self.s, self.name
        open(f"/workspace/port/out/views/{name or self.name}.html", "w").write(self.s)

# header pieces shared by auth screens
AVATAR = '<div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center"><span class="material-symbols-outlined text-on-primary text-[18px]">person</span></div>'
AVATAR_LINK = '<a href="#status" aria-label="계정" class="w-8 h-8 rounded-full bg-primary flex items-center justify-center"><span class="material-symbols-outlined text-on-primary text-[18px]">person</span></a>'
ERR = ('<div class="hidden flex items-start gap-1.5 mt-1 px-1 py-1.5 rounded-lg bg-error-container/30" id="{id}">'
       '<span class="material-symbols-outlined text-[17px] text-error shrink-0 mt-0.5" style="font-variation-settings: \'FILL\' 1;">error</span>'
       '<p class="font-body-sm text-body-sm text-on-error-container leading-tight" data-k="{id}"></p></div>')
