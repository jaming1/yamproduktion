"""Wortwurzeln für die Wurzelsuche (vereinfachter ISRI-Stemmer, ohne Wörterbuch).

Arbeitet auf bereits normalisierten Wörtern (ohne Taschkil, ا statt أ/إ/آ,
ه statt ة, ي statt ى). Ziel ist ein guter Treffer für die häufigen Muster,
nicht sprachwissenschaftliche Vollständigkeit. Beispiele:
  الصابرين → صبر, اصطبر → صبر, مصبور → صبر, يصبرون → صبر, والصبر → صبر
"""

PRE3 = ("وال", "بال", "كال", "فال", "ولل", "فلل")
PRE2 = ("ال", "لل")
SUF3 = ("تمل", "همل", "تان", "تين", "كمل")
SUF2 = ("ون", "ات", "ان", "ين", "تن", "كم", "هن", "نا", "يا", "ها", "تم", "كن", "ني", "وا", "ما", "هم")
SUF1 = ("ه", "ي", "ك", "ت", "ا", "ن")
PRE1 = ("ا", "ي", "ت", "ن")


def _strip_suffix(w, sufs, min_len):
    for s in sufs:
        if w.endswith(s) and len(w) - len(s) >= min_len:
            return w[: -len(s)]
    return w


def _pro_w4(w):
    if w[0] == "م":                       # مفعل
        return w[1:]
    if w[1] == "ا":                       # فاعل
        return w[0] + w[2:]
    if w[2] in "اوي":                     # فعال فعول فعيل
        return w[:2] + w[3]
    if w[3] == "ه":                       # فعله
        return w[:3]
    w2 = _strip_suffix(w, SUF1, 3)
    if len(w2) == 3:
        return w2
    return w[1:] if w[0] in PRE1 else w


def _pro_w5(w):
    a, b, c, d, e = w
    if e == "ه":                           # Femininendung zuerst (مكتبه، كتابه)
        return _pro_w4(w[:4])
    if d == "ا" and e == "ء":              # فعلاء (علماء)
        return a + b + c
    if a == "م" and d in "اوي":            # مفعال مفعول مفعيل
        return b + c + e
    if a == "ا" and c in "تطد":            # افتعل (اصطبر، ازدجر)
        return b + d + e
    if a == "م" and c in "تطد":            # مفتعل
        return b + d + e
    if a == "ي" and c in "تطد":            # يفتعل
        return b + d + e
    if a == "ت" and c == "ا":              # تفاعل
        return b + d + e
    if a == "م" and c == "ا":              # مفاعل
        return b + d + e
    if a == "ا" and c == "ا":              # افاعل
        return b + d + e
    if b == "ا" and d == "و":              # فاعول
        return a + c + e
    if a == "ا" and b == "ن":              # انفعل
        return w[2:]
    if a == "م" and b == "ن":              # منفعل
        return w[2:]
    if a == "ت" and b == "م":              # تمفعل
        return w[2:]
    if a == "ت" and d in "اي":             # تفعيل تفعال
        return b + c + e
    if c == "ي" and a == "م":
        return b + d + e
    w2 = _strip_suffix(w, SUF1, 4)
    if len(w2) == 4:
        return _pro_w4(w2)
    if a in PRE1 or a == "م":
        return _pro_w4(w[1:])
    return w


def _pro_w6(w):
    if w.startswith("است") or w.startswith("مست"):  # استفعل مستفعل
        return w[3:]
    if w[0] == "م" and w[3] == "ا" and w[5] == "ه":  # مفعاله
        return w[1:3] + w[4]
    if w[0] == "ا" and w[2] == "ت" and w[4] == "ا":  # افتعال
        return w[1] + w[3] + w[5]
    if w[0] == "ا" and w[3] == "ا":                  # افعوعل افعال…
        return w[1:3] + w[4]
    if w[0] == "ت" and w[2] == "ا" and w[4] == "ي":  # تفاعيل
        return w[1] + w[3] + w[5]
    w2 = _strip_suffix(w, SUF1, 5)
    if len(w2) == 5:
        return _pro_w5(w2)
    if w[0] in PRE1 or w[0] == "م":
        return _pro_w5(w[1:])
    return w


def root(word):
    """Wurzel eines normalisierten Wortes; kurze Wörter bleiben unverändert."""
    w = word
    if len(w) < 4 or not w.isalpha():
        return w
    for p in PRE3:
        if w.startswith(p) and len(w) - 3 >= 3:
            w = w[3:]
            break
    else:
        for p in PRE2:
            if w.startswith(p) and len(w) - 2 >= 3:
                w = w[2:]
                break
    if (len(w) >= 5 or (len(w) == 4 and w[1] != "ا")) and w[0] in "وف":
        w2 = w[1:]
        if len(w2) >= 3:
            w = w2
    if len(w) > 3:
        w = _strip_suffix(w, SUF3, 3)
    if len(w) > 3:
        w = _strip_suffix(w, SUF2, 3)
    if len(w) == 4:
        return _pro_w4(w)
    if len(w) == 5:
        return _pro_w5(w)
    if len(w) == 6:
        return _pro_w6(w)
    if len(w) >= 7:
        w2 = _strip_suffix(w, SUF1, 6)
        return _pro_w6(w2[:6]) if len(w2) >= 6 else w2
    return w


def build_root_table(con, log=print):
    """Wurzel für jedes Wort im Suchindex berechnen (nach jedem Import neu)."""
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS page_vocab USING fts5vocab(page_fts, 'row')")
    con.execute("DELETE FROM word_root")
    batch = []
    for term, docs in con.execute("SELECT term, doc FROM page_vocab"):
        if term.isalpha() and len(term) >= 3:
            batch.append((term, root(term), docs))
        if len(batch) >= 50000:
            con.executemany("INSERT OR REPLACE INTO word_root VALUES (?,?,?)", batch)
            batch = []
    con.executemany("INSERT OR REPLACE INTO word_root VALUES (?,?,?)", batch)
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM word_root").fetchone()[0]
    log("Wurzeltabelle: %d Wörter." % n)
    return n
