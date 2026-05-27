import os
import pandas as pd
from analyze_data import PeakInfo
from structs import Params

def save_csv_raw(data, params: Params):
    
    df = pd.DataFrame(data, columns=["Wavelength", "Power"])
    os.makedirs(os.path.join("Test Results", "Raw Data", params.date), exist_ok=True)
    file_path = os.path.join("Test Results", "Raw Data", params.date, params.csv_fname)
    df.to_csv(file_path, index=False)    
    print("Raw data saved to a file: ", file_path, "\n")
    
def save_csv_peak(peak_info: PeakInfo, params: Params):
    # Construct pandas DataFrame
    peak_dict = {
        "Label"      : [params.peak_label],
        "Timestamp"  : [params.time],
        "Wavelength" : [peak_info.csv.wl],
        "Depth (max)": [peak_info.csv.depth],
        "FWHM (max)" : [peak_info.csv.fwhm]
    }
    
    peak_df = pd.DataFrame(data=peak_dict)
    os.makedirs(os.path.join("Test Results", "Peak Analyses"), exist_ok=True) 
    csv_path = os.path.join("Test Results", "Peak Analyses", params.peak_fname)
    peak_df.to_csv(csv_path, index=False, mode='a', header=not os.path.exists(csv_path))    
    print("Peak information saved to a file: ", csv_path, "\n")