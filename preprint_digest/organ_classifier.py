"""Keyword-based organ/tissue classifier for preprint_digest.

Maps each preprint to a primary organ system by scanning its title + abstract.
Edit ORGAN_KEYWORDS directly to add, remove, or adjust organs and their keywords.
Order matters: more specific organs should appear before broad catch-alls.
"""

ORGAN_KEYWORDS = {
    "Kidney":    ["kidney", "renal", "nephron", "glomerulus", "glomerular",
                  "tubular", "podocyte", "nephric", "nephrotic"],
    "Brain":     ["brain", "neural", "neuron", "cerebral", "cortex", "hippocampus",
                  "cerebellum", "astrocyte", "microglia", "neuronal", "neuroscience",
                  "synapse", "dopamine", "hypothalamus", "brainstem"],
    "Intestine": ["intestine", "intestinal", "gut", "colon", "colonic", "duodenum",
                  "ileum", "jejunum", "enteric", "colonoid", "enteroid", "bowel",
                  "cecum", "rectum", "rectal"],
    "Liver":     ["liver", "hepatic", "hepatocyte", "hepato", "biliary",
                  "bile duct", "cholangio", "sinusoid"],
    "Heart":     ["heart", "cardiac", "cardiomyocyte", "myocardial", "cardiovascular",
                  "atrial", "ventricular", "pericardium", "aortic"],
    "Lung":      ["lung", "pulmonary", "airway", "alveolar", "bronchial",
                  "respiratory", "tracheal", "pleural", "pneumocyte"],
    "Pancreas":  ["pancreas", "pancreatic", "islet", "beta cell", "beta-cell",
                  "acinar", "ductal", "endocrine pancreas"],
    "Eye":       ["retina", "retinal", "ocular", "cornea", "optic", "photoreceptor",
                  "lens", "vitreous", "choroid", "ophthalmic"],
    "Skin":      ["skin", "dermal", "epidermal", "keratinocyte", "melanocyte",
                  "cutaneous", "dermis", "fibroblast skin"],
    "Blood":     ["hematopoietic", "haematopoietic", "erythrocyte", "platelet",
                  "myeloid", "lymphocyte", "bone marrow", "leukocyte", "neutrophil",
                  "macrophage", "dendritic cell", "T cell", "B cell", "NK cell"],
    "Muscle":    ["muscle", "myocyte", "skeletal muscle", "smooth muscle",
                  "myoblast", "myofiber", "sarcomere", "myogenesis"],
    "Bone":      ["bone", "osteocyte", "osteoblast", "osteoclast",
                  "chondrocyte", "cartilage", "skeletal", "periosteum"],
    "Breast":    ["breast", "mammary", "lactation", "mammary gland"],
    "Prostate":  ["prostate", "prostatic"],
    "Bladder":   ["bladder", "urothelial", "urinary tract"],
    "Ovary":     ["ovary", "ovarian", "follicle", "oocyte", "granulosa"],
    "Placenta":  ["placenta", "placental", "trophoblast", "chorion"],
}


def classify_organ(title: str, abstract: str) -> str:
    """Return the primary organ/tissue system for a preprint.

    Scans title + abstract (case-insensitive substring match).
    First matching organ in ORGAN_KEYWORDS wins.
    Returns "General" if no organ keyword is found.
    """
    searchable = (title + " " + abstract).lower()
    for organ, keywords in ORGAN_KEYWORDS.items():
        if any(kw in searchable for kw in keywords):
            return organ
    return "General"
