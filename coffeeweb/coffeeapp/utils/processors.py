import numpy as np
import pandas as pd
from functools import lru_cache
from django.conf import settings

# =========================
# 1) DATA PROCESSOR
# =========================
class CoffeeDataProcessor:
    """Baca Excel → normalisasi → konversi → drop duplikat → simpan density tersedia (SET)."""

    REQUIRED_COLS = ("density", "temperature", "grind size", "ratio")

    def __init__(self, excel_path=None, drop_dupes=True):
        self.excel_path = str(excel_path or settings.DATA_EXCEL_PATH)
        self.df = pd.read_excel(self.excel_path)
        self.processed_data = []
        self.available_densities = set()
        self.drop_dupes = drop_dupes

    @staticmethod
    def _to_int(val, remove=None):
        if pd.isna(val):
            raise ValueError("NaN")
        s = str(val).strip()
        if remove:
            for r in remove:
                s = s.replace(r, "")
        return int(float(s))

    def process_excel_data(self):
        # normalisasi header
        self.df.columns = [str(c).strip().lower() for c in self.df.columns]
        # cek kolom wajib
        missing = [c for c in self.REQUIRED_COLS if c not in self.df.columns]
        if missing:
            raise ValueError(f"Kolom wajib hilang di Excel: {missing}")

        # hilangkan baris duplikat (opsional)
        if self.drop_dupes:
            self.df = self.df.drop_duplicates(
                subset=["density", "temperature", "grind size", "ratio"],
                keep="first",
                ignore_index=True,
            )

        self.processed_data.clear()
        self.available_densities = set()

        for _, row in self.df.iterrows():
            try:
                density   = self._to_int(row["density"])
                temp      = self._to_int(row["temperature"], remove=["°C"])
                grindsize = self._to_int(row["grind size"], remove=["µm"])
                ratio     = self._to_int(row["ratio"], remove=["1:"])
                self.processed_data.append({
                    "density": density,
                    "temp": temp,
                    "grindsize": grindsize,
                    "ratio": ratio,
                    "source": "excel",
                })
                self.available_densities.add(density)
            except Exception:
                # skip baris bermasalah
                continue

        if not self.processed_data:
            raise ValueError("Tidak ada data valid dari Excel.")
        return self.processed_data

    def find_nearest_density(self, target_density: int):
        """Pilih density terdekat yang ADA di Excel. Digit ≥7 → naik, selain itu → turun."""
        if not self.available_densities:
            return None
        densities = sorted(self.available_densities)
        last_digit = target_density % 10
        if last_digit >= 5:
            higher = [d for d in densities if d >= target_density]
            return min(higher) if higher else max(densities)
        else:
            lower = [d for d in densities if d <= target_density]
            return max(lower) if lower else min(densities)


@lru_cache(maxsize=1)
def _get_cached_processor(excel_path=None):
    """Cache 1 instance processor agar Excel tidak dibaca berulang."""
    return CoffeeDataProcessor(excel_path or settings.DATA_EXCEL_PATH)


# =========================
# 2) FUZZY (TAHANI)
# =========================
class CoffeeFuzzySystem:
    def __init__(self):
        self.density_sets = {
            "sangat_rendah": [350, 360, 370],
            "rendah":        [370, 380, 390],
            "sedang":        [390, 400, 410, 420],
            "tinggi":        [420, 430, 440],
            "sangat_tinggi": [440, 450],
        }
        self.temp_sets = {"rendah":[90,91],"sedang":[91,92,93],"tinggi":[93,94,95,96]}
        self.grindsize_sets = {
            "sangat_halus":[500,550,600,650,700],
            "halus":[650,700,750],
            "sedang":[750,800,850,900],
            "kasar":[900,950,1000],
            "sangat_kasar":[1000,1050,1100,1150,1200,1250,1300],
        }
        self.ratio_sets = {
            "sangat_pendek":[12,13],
            "pendek":[13,14],
            "sedang":[14,15,16],
            "panjang":[16,17],
            "sangat_panjang":[17,18],
        }
        self.rules = [
            # STRONG
            {"density":"sangat_rendah","temp":"rendah","grindsize":"sedang","ratio":"sangat_pendek","strength":"strong"},
            {"density":"rendah","temp":"sedang","grindsize":"sedang","ratio":"sangat_pendek","strength":"strong"},
            {"density":"sedang","temp":"sedang","grindsize":"halus","ratio":"pendek","strength":"strong"},
            {"density":"tinggi","temp":"tinggi","grindsize":"sangat_halus","ratio":"sedang","strength":"strong"},
            {"density":"sangat_tinggi","temp":"tinggi","grindsize":"sangat_halus","ratio":"sedang","strength":"strong"},
            # MEDIUM
            {"density":"sangat_rendah","temp":"rendah","grindsize":"kasar","ratio":"sangat_pendek","strength":"medium"},
            {"density":"rendah","temp":"sedang","grindsize":"sedang","ratio":"pendek","strength":"medium"},
            {"density":"sedang","temp":"sedang","grindsize":"sedang","ratio":"sedang","strength":"medium"},
            {"density":"tinggi","temp":"tinggi","grindsize":"halus","ratio":"panjang","strength":"medium"},
            {"density":"sangat_tinggi","temp":"tinggi","grindsize":"halus","ratio":"panjang","strength":"medium"},
            # LIGHT
            {"density":"sangat_rendah","temp":"rendah","grindsize":"sangat_kasar","ratio":"pendek","strength":"light"},
            {"density":"rendah","temp":"sedang","grindsize":"kasar","ratio":"sedang","strength":"light"},
            {"density":"sedang","temp":"sedang","grindsize":"kasar","ratio":"panjang","strength":"light"},
            {"density":"tinggi","temp":"tinggi","grindsize":"sedang","ratio":"sangat_panjang","strength":"light"},
            {"density":"sangat_tinggi","temp":"tinggi","grindsize":"sedang","ratio":"sangat_panjang","strength":"light"},
        ]

    def fuzzy_membership(self, value, sets):
        membership = {}
        for set_name, set_values in sets.items():
            if not set_values:
                continue
            if value in set_values:
                membership[set_name] = 1.0
            else:
                mn, mx = min(set_values), max(set_values)
                if mn <= value <= mx:
                    membership[set_name] = 1.0
                else:
                    min_dist = min(abs(value-mn), abs(value-mx))
                    membership[set_name] = max(0, 0.7 - min_dist/100) if min_dist <= 50 else 0
        return membership

    def tahani_elimination(self, density, temp, grindsize, ratio, target_strength=None):
        dm = self.fuzzy_membership(density, self.density_sets)
        tm = self.fuzzy_membership(temp, self.temp_sets)
        gm = self.fuzzy_membership(grindsize, self.grindsize_sets)
        rm = self.fuzzy_membership(ratio, self.ratio_sets)

        best_compat, best_strength = 0.0, "medium"
        for rule in self.rules:
            if target_strength and rule["strength"] != target_strength:
                continue
            comps = [dm.get(rule["density"],0), tm.get(rule["temp"],0),
                     gm.get(rule["grindsize"],0), rm.get(rule["ratio"],0)]
            nz = [c for c in comps if c > 0]
            rule_compat = (np.exp(np.mean(np.log(nz))) if nz else 0)
            if rule_compat > best_compat:
                best_compat, best_strength = rule_compat, rule["strength"]
        return best_compat > 0.1, best_strength, float(best_compat)


# =========================
# 3) TOPSIS
# =========================
class TOPSIS:
    def __init__(self, target_strength=None):
        self.target_strength = target_strength if target_strength != "any" else None
        if self.target_strength == "strong":
            self.criteria = {'density_temp_match':{'weight':0.15,'type':'benefit'},
                             'grind_appropriateness':{'weight':0.30,'type':'benefit'},
                             'ratio_appropriateness':{'weight':0.35,'type':'benefit'},
                             'rule_compatibility':{'weight':0.20,'type':'benefit'}}
        elif self.target_strength == "light":
            self.criteria = {'density_temp_match':{'weight':0.15,'type':'benefit'},
                             'grind_appropriateness':{'weight':0.30,'type':'benefit'},
                             'ratio_appropriateness':{'weight':0.35,'type':'benefit'},
                             'rule_compatibility':{'weight':0.20,'type':'benefit'}}
        else: 
            self.criteria = {'density_temp_match':{'weight':0.15,'type':'benefit'},
                             'grind_appropriateness':{'weight':0.30,'type':'benefit'},
                             'ratio_appropriateness':{'weight':0.35,'type':'benefit'},
                             'rule_compatibility':{'weight':0.20,'type':'benefit'}}

    def calculate_scores(self, recipes):
        if not recipes:
            return []
        decision_matrix, info = [], []
        for r in recipes:
            decision_matrix.append([
                self.calculate_density_temp_match(r['density'], r['temp']),
                self.calculate_grind_appropriateness(r['density'], r['grindsize'], r['strength']),
                self.calculate_ratio_appropriateness(r['density'], r['ratio'], r['strength']),
                r['compatibility'],
            ])
            info.append(r)

        dm = np.array(decision_matrix, dtype=float)
        norm = dm / np.sqrt((dm**2).sum(axis=0))
        weights = np.array([self.criteria[k]['weight'] for k in self.criteria.keys()])
        weighted = norm * weights

        pos, neg = [], []
        for i, (_, prop) in enumerate(self.criteria.items()):
            if prop['type'] == 'benefit':
                pos.append(weighted[:, i].max()); neg.append(weighted[:, i].min())
            else:
                pos.append(weighted[:, i].min()); neg.append(weighted[:, i].max())
        pos, neg = np.array(pos), np.array(neg)
        dpos = np.sqrt(((weighted - pos)**2).sum(axis=1))
        dneg = np.sqrt(((weighted - neg)**2).sum(axis=1))
        scores = dneg / (dpos + dneg)

        results = [{'recipe': info[i], 'topsis_score': float(scores[i]), 'rank': 0}
                   for i in range(len(scores))]
        results.sort(key=lambda x: x['topsis_score'], reverse=True)
        for i, r in enumerate(results):
            r['rank'] = i + 1
        return results

    def calculate_density_temp_match(self, density, temp):
        ideal_temp = 90 + (density - 350) * (96-90) / (450-350)
        return max(0.0, 1 - abs(temp - ideal_temp)/3)

    def calculate_grind_appropriateness(self, density, grindsize, strength):
        if strength == 'strong':
            ideal = 800 - (density - 350) * (800-700) / (450-350)
        elif strength == 'light':
            ideal = 1000 - (density - 350) * (1000-800) / (450-350)
        else:
            ideal = 900 - (density - 350) * (900-750) / (450-350)
        return max(0.0, 1 - abs(grindsize - ideal)/200)

    def calculate_ratio_appropriateness(self, density, ratio, strength):
        if strength == 'strong':
            ideal = 12 + (density - 350) * (16-12) / (450-350)
        elif strength == 'light':
            ideal = 13 + (density - 350) * (18-13) / (450-350)
        else:
            ideal = 12 + (density - 350) * (17-12) / (450-350)
        return max(0.0, 1 - abs(ratio - ideal)/2)


# =========================
# 4) OPTIMIZER (Public API)
# =========================
class CoffeeRecipeOptimizer:
    """Dipakai view: find_best_recipes(density, target_strength, top_n=5)."""

    def __init__(self, excel_path=None):
        self.fuzzy_system = CoffeeFuzzySystem()
        self.data_processor = _get_cached_processor(excel_path)
        self.excel_data = self.data_processor.process_excel_data()
        if not self.excel_data:
            raise ValueError("Tidak ada data yang berhasil diproses dari Excel")

    @staticmethod
    def _unique_by(rows, keys=('temp','grindsize','ratio','strength')):
        seen, out = set(), []
        for r in rows:
            key = tuple(r[k] for k in keys)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def find_best_recipes(self, density=None, target_strength=None, top_n=5):
        if target_strength == "any":
            target_strength = None

        if density:
            actual = self.data_processor.find_nearest_density(int(density))
            filtered = [d for d in self.excel_data if d['density'] == actual]
        else:
            filtered, actual = self.excel_data, None

        # buang duplikat kombinasi supaya Top-5 tidak identik
        filtered = self._unique_by(filtered, keys=('temp','grindsize','ratio'))

        valid = []
        for r in filtered:
            ok, strength, compat = self.fuzzy_system.tahani_elimination(
                r['density'], r['temp'], r['grindsize'], r['ratio'], target_strength
            )
            if ok:
                valid.append({**r, 'strength': strength, 'compatibility': float(compat)})

        ranked = TOPSIS(target_strength).calculate_scores(valid)
        return ranked[: top_n], actual

def format_recipe_output(ranked_recipes, input_density=None, actual_density=None, target_strength=None):
    """Membuat tampilan output yang komunikatif (bisa di print atau ditampilkan di template)."""
    if not ranked_recipes:
        return "⚠️ Tidak ditemukan resep yang sesuai dengan kriteria."

    # Ambil resep terbaik (rank 1)
    best = ranked_recipes[0]['recipe']
    fuzzy_score = best.get('compatibility', 0) * 100
    topsis_score = ranked_recipes[0]['topsis_score']

    # Tampilkan header dengan pembulatan density yang informatif
    density_info = (
        f"Density: {best['density']} (input: {input_density})"
        if actual_density == input_density
        else f"Density: {best['density']} (input: {input_density} → dibulatkan ke {actual_density})"
    )

    # Rangkai teks hasil
    output = []
    output.append("=== 🏆 RESEP TERBAIK ===")
    output.append(f"• {density_info}")
    output.append(f"• Suhu Air: {best['temp']}°C")
    output.append(f"• Grind Size: {best['grindsize']} µm")
    output.append(f"• Ratio: 1:{best['ratio']}")
    output.append(f"• Strength Profile: {best['strength']}")
    output.append(f"• Tingkat Kesesuaian Fuzzy: {fuzzy_score:.1f}%")
    output.append(f"• Skor Kualitas (TOPSIS): {topsis_score:.3f}")
    output.append("\n=== 📊 5 Rekomendasi Teratas ===")
    output.append(f"{'Rank':<4} {'Density':<7} {'Temp':<5} {'Grind':<7} {'Ratio':<6} {'Strength':<8} {'Fuzzy':<8} {'TOPSIS':<8}")
    output.append("-" * 70)

    for item in ranked_recipes:
        r = item['recipe']
        output.append(
            f"{item['rank']:<4} {r['density']:<7} {r['temp']:<5} {r['grindsize']:<7} "
            f"1:{r['ratio']:<5} {r['strength']:<8} {r['compatibility']*100:6.1f}% {item['topsis_score']:.3f}"
        )

    return "\n".join(output)
