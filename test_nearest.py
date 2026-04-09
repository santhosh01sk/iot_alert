import logging
from fire_alert import find_emergency_services

logging.basicConfig(level=logging.ERROR)  

def main():
    lat = 13.010602
    lon = 80.23453

    print(f"Finding emergency services near {lat}, {lon}...")
    nearest_fires, nearest_polices = find_emergency_services(lat, lon)

    # 1. Log to text file
    log_filename = "nearest_stations_log.txt"
    with open(log_filename, "a", encoding="utf-8") as file:
        file.write("=== topic nearest ===\n")
        file.write(f"Current Location: Lat = {lat}, Lon = {lon}\n")
        
        for idx, station in enumerate(nearest_fires):
            rank = "Primary" if idx == 0 else "Backup"
            fire_log = (f"🚒 {rank} Fire Station: {station['name']}\n"
                        f"   📍 Location: Lat = {station['lat']}, Lon = {station['lon']}\n"
                        f"   📏 Distance: {station['distance_km']:.2f} km\n")
            print(f"{rank} Fire Station: {station['name']} - {station['distance_km']:.2f} km")
            file.write(fire_log)
        
        if not nearest_fires:
            print("No fire station found nearby.\n")
            file.write("🚒 Fire Stations: None found\n")
            
        for idx, station in enumerate(nearest_polices):
            rank = "Primary" if idx == 0 else "Backup"
            police_log = (f"🚓 {rank} Police Station: {station['name']}\n"
                          f"   📍 Location: Lat = {station['lat']}, Lon = {station['lon']}\n"
                          f"   📏 Distance: {station['distance_km']:.2f} km\n")
            print(f"{rank} Police Station: {station['name']} - {station['distance_km']:.2f} km")
            file.write(police_log)

        if not nearest_polices:
            print("No police station found nearby.\n")
            file.write("🚓 Police Stations: None found\n")
            
        file.write("\n")
        print(f"Successfully logged to {log_filename}")

if __name__ == "__main__":
    main()
