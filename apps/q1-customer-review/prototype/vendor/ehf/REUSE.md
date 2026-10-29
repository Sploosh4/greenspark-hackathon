# Reviewed EHF reuse

core.py, adapters.py and calibration-v1.json were copied unchanged from the standalone task-11 EHF experiment. No synthetic sample_output or synthetic 2026 temperatures were used. The upstream 37 tests passed during the read-only review. The Q1 adapter additionally enforces separate historical/replay weather cutoffs; the EHF core itself does not enforce as-of issue times.

Method reference: Nairn and Fawcett, *The Excess Heat Factor: A Metric for Heatwave Intensity and Its Use in Classifying Heatwave Severity*, https://pmc.ncbi.nlm.nih.gov/articles/PMC4306859/.

The retained experimental calibration uses 1991–2020, not the paper’s 1971–2000 period. T95 is 34.55°C. The SILO adapter pairs Tmax on day i with Tmin on day i+1. This declared experimental day convention is retained; independent equivalence to an official BoM product is not established. Severity and official category are unavailable.

The real historical interpolated weather is attributed to Queensland Government SILO and underlying Bureau of Meteorology observations, CC BY 4.0 as recorded in the supplied provenance. No weather was downloaded for Q1. The copied calibration preserves its original raw-source hash and content identifier.
