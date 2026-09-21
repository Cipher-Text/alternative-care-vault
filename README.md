# Alternative Medicine Books Collection

This repository is a personal/reference collection of books related to alternative medicine disciplines. It is intended to keep source materials together for reading, research, cataloguing, and future development of a searchable digital library.

## Current collection

All source files are kept in [`raw/`](raw/).

| File | Format | Subject / notes |
| --- | --- | --- |
| `William Boericke - Pocket Manual of Homoeopathic Materia Medica - 8th Edition (1922).epub` | EPUB | William Boericke; homoeopathic materia medica and repertory |
| `Edmund Jennings Lee - Repertory of the Characteristic Symptoms - 1889.epub` | EPUB | Edmund Jennings Lee; homoeopathic materia medica repertory |
| `Myron H. Adams - Practical Guide to Homeopathic Treatment - 1913.epub` | EPUB | Myron H. Adams; family and student guide to homeopathic treatment |
| `E. B. Nash - Homoeopathic Therapeutics (1982 reprint).epub` | EPUB | E. B. Nash; homoeopathic therapeutics |
| `James Tyler Kent - Lectures on Homoeopathic Materia Medica.epub` | EPUB | James Tyler Kent; homoeopathic materia medica lectures |
| `Constantine Hering - The Guiding Symptoms of Our Materia Medica - Volume I (1879).epub` | EPUB | Constantine Hering; homoeopathic materia medica reference |
| `হোমিওপ্যাথিক চিকিৎসা-দর্পন.epub` | EPUB | Bengali homoeopathic reference; metadata date 1303 BS |
| `Samuel Hahnemann - Organon of Medicine.pdf` | PDF | Samuel Hahnemann; digitized edition from the Internet Archive |

## Repository structure

Original book files are kept in `raw/`. As the collection grows, discipline-specific copies or processed versions can be grouped like this:

```text
raw/
├── ayurveda/
├── herbal-medicine/
├── homeopathy/
├── traditional-medicine/
└── other/
```

Metadata should be maintained separately in a catalogue file, for example `catalogue.csv` or `catalogue.json`, with fields such as:

- title
- author
- language
- discipline
- publication year
- edition
- format
- source
- copyright/licence status

## Adding a book

1. Place the original, unmodified file in `raw/`.
2. Confirm that the book may legally be stored and shared in this repository.
3. Use a descriptive filename: `Author - Title - Edition.ext`.
4. Preserve the original file format where possible.
5. Add the book to the collection table and catalogue metadata.
6. Do not commit passwords, private documents, or unrelated files.

## Important note

This repository is for educational and archival reference only. The books do not replace qualified medical advice, diagnosis, or treatment. Do not use the collection to self-diagnose, delay urgent care, or change prescribed treatment without consulting a licensed healthcare professional.

## Copyright and licensing

The current collection consists of open-source and public-domain books intended for lawful reading, reference, and sharing. When adding future materials, record the applicable source and licence information in the catalogue.
