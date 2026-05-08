

| script                                  | description                                                                                                                                                                                                                                                                                                                                                                                                                               |
|-----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `00_harvest_all_occurrence_data.py`     | This script finds the EDITO occurrence parquet and loops over all unique dasids, creating a folder `../data/0.harvest_all_occurrence_data` and saving each dasid as its own CSV with columns latitude, longitude, observationdate, aphiaid.                                                                                                                                                                                               |
| `01_harvest_bioflow_occurrence_data.py` | This script finds the EDITO occurrence parquet and loops over all datasets from DTO-Bioflow using dasids. The dasids are stored in `/sources/...` The results are stored in 2 directories that will be created: `../data/1_harvest_wp2_observation_data` and `../data/2_harvest_wp3_sensor_observation_data`. In each directory, the datasets are stored each in separate CSV with columns latitude, longitude, observationdate, aphiaid. |
| `02_harvest_etn_data.py`                |                                                                                                                                                                                                                                                                                                                                                                                                                                           | 





