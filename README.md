# 📂 MPSIMS Data Folder

Drop your 4 MPSIMS Excel files here. The app will detect and load them automatically on startup.

## Required Files

| File | Sector |
|------|--------|
| `MPSIMSAgriculturePlanYear25-26.xlsx` | Agriculture |
| `MPSIMSScheelEducationPlanYear25-26.xlsx` | Education |
| `MPSIMSSkillPlanYear25-26.xlsx` | Skills |
| `MPSIMSSociaslJusticePlanYear25-26.xlsx` | Social Justice |

## How Detection Works

The app matches files by keyword in the filename (case-insensitive):
- File containing `agriculture` → Agriculture sector
- File containing `education` → Education sector  
- File containing `skill` → Skills sector
- File containing `social` → Social Justice sector

## After Adding Files

1. Save your Excel files to this folder
2. Restart the app: `streamlit run app.py`
3. The dashboard will auto-load all detected files — no upload needed!

To reload without restarting, click **🔄 Re-scan data/ folder** in the sidebar.
"# MPSIMS" 
