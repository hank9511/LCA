# Code availability

This repository is the **public modeling pipeline** used with openLCA:

Excel inventory → processes / product system → impact assessment.

Provider selection in this snapshot uses **semantic name matching** among database candidates, plus Excel-specified providers and market/geography filters.

**Provider screening by the pedigree-matrix method**, as used for the paper’s main results, is **not included**. After publication it will be available for **academic, non-commercial use upon email request**. Full source used in the study will be shared with editors and reviewers during peer review under confidentiality.

## Suggested manuscript wording

> The automated LCA modeling pipeline (Excel parsing, product-system construction, semantic provider matching, and LCIA via openLCA IPC) is available at https://github.com/hank9511/LCA. Provider screening by the pedigree-matrix method, as used for the main results, is withheld until publication and will thereafter be available for academic, non-commercial use upon request.

## License

Code in this public snapshot is released under the MIT License (see `LICENSE`). Access to the withheld pedigree-matrix provider-screening implementation is separate and non-commercial.
