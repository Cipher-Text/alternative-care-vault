# Alternative Medicine Books Collection

This repository is a personal/reference collection of books related to alternative medicine disciplines. It is intended to keep source materials together for reading, research, cataloguing, and future development of a searchable digital library.

## Current collection

The collection currently contains 14 valid works. Homeopathy books are kept in [`raw/homeopathy/`](raw/homeopathy/), Ayurveda books in [`raw/ayurveda/`](raw/ayurveda/), and Unani materials in [`raw/unani/`](raw/unani/).

| File | Format | Subject / notes |
| --- | --- | --- |
| `W. A. Dewey - Practical Homoeopathic Therapeutics - 1900.epub` | EPUB | W. A. Dewey; practical homoeopathic therapeutics |
| `Count Cesare Mattei - Electro-Homoeopathic Medicine - A New Medical System Being a Popular and Domestic Guide Founded on Experience - 2nd Edition (1891).epub` | EPUB | Count Cesare Mattei; electro-homoeopathic medicine |
| `E. A. Farrington - Clinical Materia Medica - 4th Edition (1908).epub` | EPUB | E. A. Farrington; clinical homoeopathic materia medica |
| `Andrew Lockie - Encyclopedia of Homeopathy - Updated Edition (2006).epub` | EPUB | Andrew Lockie; homeopathy reference guide |
| `Timothy Field Allen - Handbook of Materia Medica and Homoeopathic Therapeutics - 1889.epub` | EPUB | Timothy Field Allen; materia medica and homoeopathic therapeutics |
| `Edmund Jennings Lee - Repertory of the Characteristic Symptoms, Clinical and Pathogenetic, of the Homoeopathic Materia Medica - 1889.epub` | EPUB | Edmund Jennings Lee; homoeopathic materia medica repertory |
| `Myron H. Adams - Practical Guide to Homeopathic Treatment - 1913.epub` | EPUB | Myron H. Adams; family and student guide to homeopathic treatment |
| `Constantine Hering - The Guiding Symptoms of Our Materia Medica - Volume I (1879).epub` | EPUB | Constantine Hering; homoeopathic materia medica reference |
| `ক্লিনিক্যাল মেটেরিয়া মেডিকা.epub` | EPUB | Bengali clinical materia medica reference; author and publication date not identified |
| `হোমিওপ্যাথিক চিকিৎসা-দর্পন.epub` | EPUB | Bengali homoeopathic reference; metadata date 1303 BS |
| `Samuel Hahnemann - Organon of Medicine.pdf` | PDF | Samuel Hahnemann; digitized edition from the Internet Archive |
| `Ashtanga Hridaya Vagbhatta English Trans Srikantha Murthy K.R. Vol 1 Chowkambha.epub` | EPUB | Ayurveda; English translation of the Ashtanga Hridaya, Volume I |
| `Sushruta - An English Translation of the Sushruta Samhita - Volume II - Edited by Kunjalal Bhishagratna (1911).epub` | EPUB | Sushruta Samhita; Ayurveda; edited by Kunjalal Bhishagratna |
| `Charaka Samhita - English Translation by Abinash Chandra Kaviratna - 1892.epub` | EPUB | Charaka-Samhita; Ayurveda; English translation by Abinash Chandra Kaviratna |

### Pending validation

`raw/unani/Ibn Sina - The Canon of Medicine.epub` is currently an empty 0-byte placeholder and is excluded from the collection count. Replace it with a valid EPUB or PDF before cataloguing it.

## Repository structure

The current collection is organized by discipline. Additional disciplines can use their own directories:

```text
raw/
├── ayurveda/
├── homeopathy/
└── unani/
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

1. Place the original, unmodified file in the appropriate `raw/<discipline>/` directory.
2. Confirm that the book may legally be stored and shared in this repository.
3. Use a descriptive filename: `Author - Title - Edition.ext`.
4. Preserve the original file format where possible.
5. Add the book to the collection table and catalogue metadata.
6. Do not commit passwords, private documents, or unrelated files.

## Important note

This repository is for educational and archival reference only. The books do not replace qualified medical advice, diagnosis, or treatment. Do not use the collection to self-diagnose, delay urgent care, or change prescribed treatment without consulting a licensed healthcare professional.

## Copyright and licensing

Some older works in the collection may be public domain, but the copyright and licence status of every file has not been independently verified. Confirm that a book may legally be stored and shared before adding or redistributing it, and record the applicable source and licence information in the catalogue.
