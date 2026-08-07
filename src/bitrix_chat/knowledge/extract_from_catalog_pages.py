"""Extract products from astopt.ru category pages and build catalog."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Build regex to match [name](\catalog\path\id) or [name](/catalog/path/id)
# The .md files use backslash: \catalog\detskaya-odezhda\futbolki\382932
_bs = re.escape("\\")  # escaped single backslash
PRODUCT_LINK_RE = re.compile(rf"\[([^\]]+)\]\((?:{_bs}|/)catalog(?:{_bs}|/)([^)]+)\)")

STOCK_RE = re.compile(r"Есть в наличии:\s*(\d+)")
PRICE_RE = re.compile(r"([\d\s]+)\s*тенге")
PACK_RE = re.compile(r"В упак:\s*(\d+)\s*шт\s*\|\s*([\d\s]+)\s*тенге/шт")

NAME_MAP = {
    "detskaya-odezhda": "Детская одежда",
    "futbolki": "Футболки",
    "kostyumy-letnie": "Костюмы летние",
    "kostyumy-mezhsezonnye-vsesezonnye": "Костюмы межсезонные/всесезонные",
    "kostyumy-zimnie": "Костюмы зимние",
    "odezhda": "Одежда",
    "shorty": "Шорты",
    "shorty-kupalnye": "Шорты купальные",
    "platya": "Платья",
    "platya-naryadnye": "Платья нарядные",
    "platya-povsednevnye": "Платья повседневные",
    "kofty": "Кофты",
    "kofty-zhiletki": "Кофты/жилетки",
    "svitera-kardigany-khudi-tuniki": "Свитера/кардиганы/худи/туники",
    "losiny": "Лосины",
    "losiny-gimnasticheskie": "Лосины гимнастические",
    "shtany-triko": "Штаны/трико",
    "dzhinsy-dzhegginsy": "Джинсы/джеггинсы",
    "dzhoggery-klesh": "Джоггеры/клеш",
    "shorty-shtany": "Шорты/штаны",
    "longslivy-vodolazki": "Лонгсливы/водолазки",
    "longslivy": "Лонгсливы",
    "tenniski": "Тенниски",
    "velosipedki": "Велосипедки",
    "yubki": "Юбки",
    "pizhamy": "Пижамы",
    "kupalniki-dlya-plavaniya": "Купальники для плавания",
    "kupalniki-gimnasticheskie": "Купальники гимнастические",
    "plavki-trusy-dlya-kupaniya": "Плавки/трусы для купания",
    "khalaty": "Халаты",
    "polzunki": "Ползунки",
    "raspashonki": "Распашонки",
    "bodi-dlinnyy-rukav": "Боди длинный рукав",
    "bodi-futbolki": "Боди-футболки",
    "bodi-korotkiy-rukav": "Боди короткий рукав",
    "bodi-mayki": "Боди-майки",
    "bodi-platya": "Боди-платья",
    "bodi-raspashonki": "Боди-распашонки",
    "futbolki_1": "Футболки",
    "kardigany-sarafany-rubashki-bluzki": "Кардиганы/сарафаны/рубашки/блузки",
    "pesochniki": "Песочники",
    "chepchiki-i-shapki": "Чепчики и шапки",
    "kombinezony": "Комбинезоны",
    "kombinezony_1": "Комбинезоны",
    "kostyumy": "Костюмы",
    "kostyumy-letnie_1": "Костюмы летние",
    "kostyumy-mezhsezonnye-i-vsesezonnye": "Костюмы межсезонные и всесезонные",
    "kostyumy-zimnie_1": "Костюмы зимние",
    "pelenki": "Пелёнки",
    "pelenki-polotentsa-pledy-podushki": "Пелёнки/полотенца/пледы/подушки",
    "odelyao-pledy": "Одеяла и пледы",
    "aksessuary": "Аксессуары",
    "bafy-manishki-dlya-detey": "Бафы/манишки для детей",
    "bafy-manishki-dlya-vzroslykh": "Бафы/манишки для взрослых",
    "galstuki-babochki-bantiki": "Галстуки/бабочки/бантики",
    "naushniki": "Наушники",
    "palantiny": "Палантины",
    "perchatki": "Перчатки",
    "platki": "Платки",
    "prochie-aksessuary": "Прочие аксессуары",
    "sharfy-dlya-detey": "Шарфы для детей",
    "sharfy-dlya-vzroslykh": "Шарфы для взрослых",
    "snudy": "Снуды",
    "varezhki": "Варежки",
    "igrushki": "Игрушки",
    "igrushki_glina-plastilin": "Глина/пластилин",
    "igrushki_konstruktory": "Конструкторы",
    "igrushki_kukhnya-muzykalnyy-telefon-tualetnyy-stolik": "Кухня/музыкальный телефон/туалетный столик",
    "igrushki_minifigurki-antistress": "Минифигурки/антистресс",
    "igrushki_myachi-nasosy": "Мячи/насосы",
    "igrushki_nabory-dlya-risovaniya": "Наборы для рисования",
    "igrushki_nabory-kosmetiki-nabory-posudy": "Наборы косметики/наборы посуды",
    "igrushki_pazly-razvivayushchie-igrushki": "Пазлы/развивающие игрушки",
    "igrushki_pesochnye-nabory": "Песочные наборы",
    "igrushki_prochie-igrushki": "Прочие игрушки",
    "igrushki_prochie-nabory-igrushek": "Прочие наборы игрушек",
    "igrushki_talakary-mashinki-roboty": "Талакары/машинки/роботы",
    "obuv": "Обувь",
    "cheshki": "Чешки",
    "krossovki": "Кроссовки",
    "sandali": "Сандалии",
    "shkolnaya-odezhda": "Школьная одежда",
    "bluzki-rubashki-dlya-devochek": "Блузки/рубашки для девочек",
    "bombery": "Бомберы",
    "bryuki": "Брюки",
    "dzhempery": "Джемперы",
    "kofty_1": "Кофты",
    "obmanki": "Обманки",
    "rubashki-dlya-malchikov": "Рубашки для мальчиков",
    "slaksy": "Слаксы",
    "yubki-kyuloty-sarafany": "Юбки/кюлоты/сарафаны",
    "zhiletki_1": "Жилетки",
    "verkhnyaya-odezhda": "Верхняя одежда",
    "polukombinezony": "Полукомбинезоны",
    "vetrovki-dzhinsovki": "Ветровки/джинсовки",
    "zhiletki": "Жилетки",
    "komplekty_2": "Комплекты",
    "golovnye-ubory-letnie": "Головные уборы летние",
    "golovnye-ubory-mezhsezonnye": "Головные уборы межсезонные",
    "golovnye-ubory-zimnie": "Головные уборы зимние",
    "bandany": "Банданы",
    "berety_1": "Береты",
    "berety_2": "Береты",
    "berety": "Береты",
    "chalma": "Чалма",
    "chalma_1": "Чалма",
    "dokery": "Докеры",
    "kepi": "Кепки",
    "kepki_detskie_2": "Кепки детские",
    "kepki_malyshi_2": "Кепки малыши",
    "kepki_odnotonnye": "Кепки однотонные",
    "kepki_vzroslye_2": "Кепки взрослые",
    "kepki": "Кепки",
    "kosynki": "Косынки",
    "kosynki_1": "Косынки",
    "kozyrki": "Козырьки",
    "panamy_1": "Панамы",
    "panamy_1_detskie_3": "Панамы детские",
    "panamy_1_malyshi_3": "Панамы малыши",
    "panamy_1_vzroslye_3": "Панамы взрослые",
    "panamy_2": "Панамы",
    "panamy": "Панамы",
    "povyazki": "Повязки",
    "povyazki_1": "Повязки",
    "shapki_5": "Шапки",
    "shapki_6": "Шапки",
    "shapki-trikotazhnye": "Шапки трикотажные",
    "shapki_4": "Шапки",
    "shapki_4_detskie_1": "Шапки детские",
    "shapki_4_malyshi_1": "Шапки малыши",
    "shapki_4_vzroslye_1": "Шапки взрослые",
    "shlemy": "Шлемы",
    "shlemy_1": "Шлемы",
    "ushanki": "Ушанки",
    "ushanki_1": "Ушанки",
    "ushanki_2": "Ушанки",
    "shlyapy-sumki-plyazhnye": "Шляпы/сумки/пляжные",
    "shlyapy": "Шляпы",
    "sumki-plyazhnye": "Сумки пляжные",
    "kapory": "Капоры",
    "kapory_1": "Капоры",
    "kartuzy": "Картузы",
    "kepki-uteplennye": "Кепки утеплённые",
    "kepki-uteplennye_muzhskie": "Кепки утеплённые мужские",
    "kepki-uteplennye_zhenskie": "Кепки утеплённые женские",
    "komplekty": "Комплекты",
    "komplekty_detskie": "Комплекты детские",
    "komplekty_malyshi": "Комплекты малыши",
    "komplekty_vzroslye": "Комплекты взрослые",
    "komplekty-trikotazhnye": "Комплекты трикотажные",
    "balaklavy": "Балаклавы",
    "balaklavy_1": "Балаклавы",
    "chepchiki_1": "Чепчики",
    "bel": "Бельё",
    "belo": "Бельё",
    "boksery": "Боксеры",
    "byuste": "Бюстгальтеры",
    "mayki": "Майки",
    "topy": "Топы",
    "trusiki-dlya-devochek": "Трусики для девочек",
    "trusy-dlya-malchikov": "Трусы для мальчиков",
    "trusy-shortiki-dlya-devochek": "Трусы/шортики для девочек",
    "chulochno-nosochnye-izdeliya": "Чулочно-носочные изделия",
    "gamashi-legginsy": "Гамаши/леггинсы",
    "golfy-sledki": "Гольфы/следки",
    "kalsony": "Кальсоны",
    "kolgotki": "Колготки",
    "noski": "Носки",
    "aksessuary-k-odezhde": "Аксессуары к одежде",
    "aksessuary_odezhdy": "Аксессуары одежды",
    "aksessuary-i-igrushki": "Аксессуары и игрушки",
    "molokootsosy": "Молокоотсосы",
    "nebulayzery": "Небулайзеры",
    "niblery": "Ниблеры",
    "pinetki": "Пинетки",
    "podguzniki-eko-trusiki-vkladyshi-dlya-pampersov": "Подгузники/эко-трусики/вкладыши",
    "posuda": "Посуда",
    "prorezyvateli-derzhateli-pustyshek-pogremushki-nabory-aksessuarov": "Прорезыватели/держатели/пустышки/погремушки",
    "pustyshki-soski": "Пустышки/соски",
    "slyunyavchiki": "Слюнявчики",
    "sumki-dlya-roddoma": "Сумки для роддома",
    "trimmery": "Триммеры",
    "tsarapki-shapka-ochki": "Царапки/шапка/очки",
    "vkladyshi-dlya-grudi": "Вкладыши для груди",
    "nakidki-dlya-komleniya-dozatory-aspiratory": "Накидки для кормления/доzаторы/аспираторы",
    "kozyrki-dlya-kupaniya": "Козырьки для купания",
    "lyulki": "Люльки",
    "dlya-novorozhdennykh": "Для новорождённых",
}


def parse_category_path(url_path: str) -> str:
    """Convert URL path to human-readable category path."""
    # Remove leading \\ or / and catalog prefix
    cleaned = re.sub(r"^(\\\\|/)+catalog(\\\\|/)+", "", url_path)
    # Remove query params
    cleaned = cleaned.split("?")[0]
    # Split by backslash or forward slash
    parts = [p for p in re.split(r"[\\/]", cleaned) if p]
    # Remove product ID (last numeric part)
    if parts and parts[-1].isdigit():
        parts = parts[:-1]

    readable_parts = []
    for part in parts:
        if part in NAME_MAP:
            readable_parts.append(NAME_MAP[part])
        else:
            matched = False
            for key, value in NAME_MAP.items():
                if key.lower() == part.lower():
                    readable_parts.append(value)
                    matched = True
                    break
            if not matched:
                readable_parts.append(part.replace("-", " ").replace("_", " ").title())

    return " > ".join(readable_parts)


def extract_products_from_category(filepath: Path) -> list[dict]:
    """Extract all products from a single category .md file."""
    content = filepath.read_text(encoding="utf-8")
    products = []

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        link_match = PRODUCT_LINK_RE.search(line)
        if link_match:
            product_name = link_match.group(1).strip()
            url_path = link_match.group(2).strip()

            # Extract product ID (last numeric segment)
            path_parts = [p for p in re.split(r"[\\/]", url_path.split("?")[0]) if p]
            product_id = (
                path_parts[-1] if path_parts and path_parts[-1].isdigit() else None
            )
            # Build clean URL (replace backslashes with forward slashes)
            clean_path = url_path.split("?")[0].replace("\\", "/")
            product_url = (
                f"https://astopt.ru/catalog/{clean_path}" if product_id else None
            )

            stock = None
            price = None
            pack_qty = None
            price_per_unit = None
            sku = None

            for j in range(i + 1, min(i + 15, len(lines))):
                look_line = lines[j].strip()

                stock_match = STOCK_RE.search(look_line)
                if stock_match:
                    stock = int(stock_match.group(1))

                if price is None:
                    price_match = PRICE_RE.search(look_line)
                    if price_match:
                        price_str = price_match.group(1).replace(" ", "").strip()
                        try:
                            price = float(price_str)
                        except ValueError:
                            pass

                pack_match = PACK_RE.search(look_line)
                if pack_match:
                    pack_qty = int(pack_match.group(1))
                    ppu_str = pack_match.group(2).replace(" ", "").strip()
                    try:
                        price_per_unit = float(ppu_str)
                    except ValueError:
                        pass

            sku_match = re.search(r"арт\.(\S+)", product_name)
            if sku_match:
                sku = sku_match.group(1)

            category_path = parse_category_path(url_path)

            if product_name and price is not None:
                products.append(
                    {
                        "name": product_name,
                        "price": price,
                        "stock": stock,
                        "pack_qty": pack_qty,
                        "price_per_unit": price_per_unit,
                        "sku": sku,
                        "category_path": category_path,
                        "url": product_url,
                        "source_file": filepath.name,
                    }
                )

        i += 1

    return products


def main() -> None:
    crawl_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("crawl_output")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("knowledge/catalog")

    if not crawl_dir.exists():
        print(f"Error: {crawl_dir} not found", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    category_files = sorted(crawl_dir.glob("catalog_*.md"))
    print(f"Scanning {len(category_files)} category files...")

    all_products = []
    seen_urls = set()

    for filepath in category_files:
        products = extract_products_from_category(filepath)
        for product in products:
            url_key = product.get("url") or product["name"]
            if url_key not in seen_urls:
                seen_urls.add(url_key)
                all_products.append(product)

    all_products.sort(key=lambda p: (p.get("category_path") or "", p.get("name") or ""))

    json_path = output_dir / "catalog.json"
    json_path.write_text(
        json.dumps(all_products, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_path = output_dir / "catalog.md"
    lines = [
        "# Каталог товаров АстанаОптТорг",
        "",
        f"Всего товаров: {len(all_products)}",
        "",
    ]

    current_category = None
    for product in all_products:
        cat = product.get("category_path") or "Без категории"
        if cat != current_category:
            current_category = cat
            lines.extend(["", f"## {cat}", ""])

        name = product.get("name") or "Без названия"
        price = (
            f"{product['price']:,.0f} тенге"
            if product.get("price")
            else "Цена не указана"
        )
        stock = product.get("stock")
        sku = product.get("sku")
        pack_info = ""
        if product.get("pack_qty") and product.get("price_per_unit"):
            pack_info = f" (В упак: {product['pack_qty']} шт | {product['price_per_unit']:,.0f} тенге/шт)"

        lines.extend(
            [
                f"### {name}",
                "",
                f"**Цена:** {price}{pack_info}",
            ]
        )
        if stock is not None:
            lines.append(f"**Остаток:** {stock} шт")
        if sku:
            lines.append(f"**Артикул:** {sku}")
        if product.get("url"):
            lines.extend(["", f"[Подробнее]({product['url']})"])
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    categories = {}
    for p in all_products:
        cat = p.get("category_path") or "Без категории"
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\nExtracted {len(all_products)} unique products")
    print(f"Categories: {len(categories)}")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

    print(f"\nJSON: {json_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
