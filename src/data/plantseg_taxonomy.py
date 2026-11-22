"""PlantSeg's plant/disease taxonomy, copied verbatim from the dataset's own source.

CLASSES is copied byte-for-byte from `mmseg/datasets/plantseg115.py` in the
PlantSeg repo (https://github.com/tqwei05/PlantSeg, fetched 2026-10-01), where
it is the METAINFO["classes"] tuple used by their mmsegmentation dataset class.
Index 0 is an unused "" placeholder (background/ignore label); indices 1-115
are the 115 disease classes. We keep that indexing so category_id (0-114 in
the COCO annotation files) + 1 lines up with CLASSES, matching how mmseg's
dataset classes are defined.

Each class name is "<plant> <disease>". Plant names are almost always the
first word, with two documented exceptions handled in `plant_of`:
"bell pepper" (two-word plant name) and "grapevine" (treated as an alias of
"grape", since it's the same plant - PlantSeg just uses the vine-specific
name for one disease, "grapevine leafroll disease").
"""

CLASSES: tuple[str, ...] = (
    "",
    "apple black rot", "apple mosaic virus", "apple rust", "apple scab",
    "banana anthracnose", "banana black leaf streak", "banana bunchy top",
    "banana cigar end rot", "banana cordana leaf spot", "banana panama disease",
    "basil downy mildew",
    "bean halo blight", "bean mosaic virus", "bean rust",
    "bell pepper bacterial spot", "bell pepper blossom end rot",
    "bell pepper frogeye leaf spot", "bell pepper powdery mildew",
    "blueberry anthracnose", "blueberry botrytis blight", "blueberry mummy berry",
    "blueberry rust", "blueberry scorch",
    "broccoli alternaria leaf spot", "broccoli downy mildew", "broccoli ring spot",
    "cabbage alternaria leaf spot", "cabbage black rot", "cabbage downy mildew",
    "carrot alternaria leaf blight", "carrot cavity spot", "carrot cercospora leaf blight",
    "cauliflower alternaria leaf spot", "cauliflower bacterial soft rot",
    "celery anthracnose", "celery early blight",
    "cherry leaf spot", "cherry powdery mildew",
    "citrus canker", "citrus greening disease",
    "coffee berry blotch", "coffee black rot", "coffee brown eye spot", "coffee leaf rust",
    "corn gray leaf spot", "corn northern leaf blight", "corn rust", "corn smut",
    "cucumber angular leaf spot", "cucumber bacterial wilt", "cucumber powdery mildew",
    "eggplant cercospora leaf spot", "eggplant phomopsis fruit rot", "eggplant phytophthora blight",
    "garlic leaf blight", "garlic rust",
    "ginger leaf spot", "ginger sheath blight",
    "grape black rot", "grape downy mildew", "grape leaf spot", "grapevine leafroll disease",
    "lettuce downy mildew", "lettuce mosaic virus",
    "maple tar spot",
    "peach anthracnose", "peach brown rot", "peach leaf curl", "peach rust", "peach scab",
    "plum bacterial spot", "plum brown rot", "plum pocket disease", "plum pox virus", "plum rust",
    "potato early blight", "potato late blight",
    "raspberry fire blight", "raspberry gray mold", "raspberry leaf spot", "raspberry yellow rust",
    "rice blast", "rice sheath blight",
    "soybean bacterial blight", "soybean brown spot", "soybean downy mildew",
    "soybean frog eye leaf spot", "soybean mosaic", "soybean rust",
    "squash powdery mildew",
    "strawberry anthracnose", "strawberry leaf scorch",
    "tobacco blue mold", "tobacco brown spot", "tobacco frogeye leaf spot", "tobacco mosaic virus",
    "tomato bacterial leaf spot", "tomato early blight", "tomato late blight", "tomato leaf mold",
    "tomato mosaic virus", "tomato septoria leaf spot", "tomato yellow leaf curl virus",
    "wheat bacterial leaf streak (black chaff)", "wheat head scab", "wheat leaf rust",
    "wheat loose smut", "wheat powdery mildew", "wheat septoria blotch",
    "wheat stem rust", "wheat stripe rust",
    "zucchini bacterial wilt", "zucchini downy mildew", "zucchini powdery mildew",
    "zucchini yellow mosaic virus",
)

assert len(CLASSES) == 116, f"expected 116 entries (1 placeholder + 115 diseases), got {len(CLASSES)}"

# Candidate crop name (as used in configs) -> plant name(s) it maps
# to in CLASSES. "chilli/pepper" only matches "bell pepper" - PlantSeg has no
# separate chilli pepper category. "cotton" and "mango" have no matches at all
# (not covered by PlantSeg); they are listed here so the stats script reports
# them as zero rather than silently skipping them.
CROP_ALIASES: dict[str, tuple[str, ...]] = {
    "tomato": ("tomato",),
    "chilli/pepper": ("bell pepper",),
    "rice": ("rice",),
    "potato": ("potato",),
    "maize/corn": ("corn",),
    "wheat": ("wheat",),
    "cotton": (),
    "grape": ("grape", "grapevine"),
    "mango": (),
    "banana": ("banana",),
}

_TWO_WORD_PLANTS = {"bell pepper"}
_PLANT_ALIASES = {"grapevine": "grape"}


def plant_of(class_name: str) -> str:
    """Return the plant name prefix of a PlantSeg disease class name.

    Handles the "bell pepper" (two-word plant) exception and normalises
    "grapevine" to "grape" (same plant, see module docstring).
    """
    for two_word in _TWO_WORD_PLANTS:
        if class_name.startswith(two_word):
            return two_word
    plant = class_name.split(" ", 1)[0]
    return _PLANT_ALIASES.get(plant, plant)


def class_name_from_file_name(file_name: str) -> str | None:
    """Recover the PlantSeg class name from an image file_name.

    File names look like "apple_black_rot_1.jpg" or
    "apple_black_rot_google_0005.jpg" - i.e. the class name with spaces
    replaced by underscores, followed by "_<id>" or "_google_<id>". Matches
    against the longest class name first so e.g. "bell pepper bacterial spot"
    isn't short-circuited by a shorter false prefix.
    """
    stem = file_name.rsplit(".", 1)[0]
    for class_name in sorted(CLASSES[1:], key=len, reverse=True):
        prefix = class_name.replace(" ", "_") + "_"
        if stem.startswith(prefix):
            return class_name
    return None
