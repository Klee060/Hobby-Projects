# -*- coding: utf-8 -*-
"""
Created on Mon Apr 21 11:21:20 2025

@author: bdmsp
"""

#open anaconda prompt
#cd <current location of this script>
#streamlit run <script name>.py   (use " " is there is spacing in script name)

# route_optimizer.py

import os
import re
import urllib.parse
import requests
import folium
import streamlit as st
import pandas as pd
from streamlit_folium import folium_static
import time
import polyline
from folium.plugins import BeautifyIcon
import streamlit.components.v1 as components

# ====== CONFIG ======
API_KEY = 'AIzaSyCWl6fip1_w5WST26D1X7GPLUgb2X5IfJc'  # <-- Replace with your API Key
DEFAULT_SUBZONE = 'Tampines'  # <-- Default subzone for address cleaning

GOOGLE_PLACES_ENDPOINT = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"

# ====== FUNCTIONS ======

def expand_short_link(url):
    """Expand shortened maps.app.goo.gl links."""
    try:
        response = requests.head(url, allow_redirects=True)
        return response.url
    except Exception as e:
        raise Exception(f"Failed to expand URL: {str(e)}")

def parse_google_maps_url(url):
    """Extract stops from Google Maps URL."""
    if "maps.app.goo.gl" in url:
        url = expand_short_link(url)

    pattern = r'/maps/dir/(.+)'
    match = re.search(pattern, url)
    
    if not match:
        raise ValueError("Invalid Google Maps URL format.")

    path = match.group(1)
    stops = path.split('/')
    stops = [urllib.parse.unquote_plus(stop) for stop in stops if stop and not (stop.startswith('@') or stop.startswith('data='))]

    if len(stops) < 2:
        raise ValueError("At least origin and destination must be provided.")

    return stops

def clean_address_with_subzone(address, default_subzone="Tampines"):
    """Ensure address includes subzone and Singapore."""
    keywords = ["Singapore", "Tampines", "Bedok", "Yishun", "Jurong", "Choa Chu Kang", "Bukit Batok", "Hougang", "Sengkang", "Woodlands"]
    if not any(kw.lower() in address.lower() for kw in keywords):
        return f"{address}, {default_subzone}, Singapore"
    return address

def improve_place_name(place_text):
    """Use Places API to improve place name."""
    GOOGLE_PLACES_ENDPOINT = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": place_text,
        "inputtype": "textquery",
        "fields": "name",
        "key": API_KEY
    }
    try:
        response = requests.get(GOOGLE_PLACES_ENDPOINT, params=params)
        result = response.json()
        if result["status"] == "OK" and result["candidates"]:
            return result["candidates"][0]["name"]
    except Exception:
        pass
    return place_text

def safe_encode(text):
    return urllib.parse.quote_plus(text)

def get_optimized_route(origin, destination, waypoints, mode="driving"):
    """Call Directions API."""
    endpoint = 'https://maps.googleapis.com/maps/api/directions/json'
    params = {
        'origin': safe_encode(origin),
        'destination': safe_encode(destination),
        'key': API_KEY,
        'mode': mode
    }
    if waypoints:
        params['waypoints'] = 'optimize:true|' + '|'.join([safe_encode(wp) for wp in waypoints])

    response = requests.get(endpoint, params=params)
    result = response.json()

    if result['status'] != 'OK':
        raise Exception(f"Directions API error: {result['status']} - {result.get('error_message', '')}")
    
    return result

def summarize_route(route_data, waypoint_names):
    """Summarize the route."""
    legs = route_data['routes'][0]['legs']
    total_distance = sum(leg['distance']['value'] for leg in legs) / 1000
    total_duration = sum(leg['duration']['value'] for leg in legs) / 60

    return {
        'total_distance_km': round(total_distance, 2),
        'total_duration_min': round(total_duration, 2),
        'start_place': waypoint_names[0],
        'end_place': waypoint_names[-1]
    }

def build_google_maps_link(origin, waypoints, destination, waypoint_order=None):
    """Build sharable Google Maps URL."""
    all_stops = [origin] + waypoints + [destination]
    if waypoint_order:
        reordered = [waypoints[i] for i in waypoint_order]
        all_stops = [origin] + reordered + [destination]
    encoded_stops = [urllib.parse.quote_plus(stop) for stop in all_stops]
    return "https://www.google.com/maps/dir/" + "/".join(encoded_stops)

def copy_to_clipboard_button(text, label="Copy Google Maps Link"):
    components.html(f"""
        <input type="text" value="{text}" id="copyText" style="opacity:0;position:absolute;left:-9999px;">
        <button onclick="navigator.clipboard.writeText(document.getElementById('copyText').value); 
        alert('Link copied to clipboard! Paste it into Google Maps.')">{label}</button>
    """, height=50)

def plot_route(route_data, waypoint_names):
    colors = ["blue", "green", "red", "orange", "purple", "darkred", "darkblue", "cadetblue", "darkgreen"]
    route = route_data['routes'][0]
    legs = route['legs']
    waypoint_order = route.get('waypoint_order', [])

    reordered_waypoint_names = [waypoint_names[0]] + [waypoint_names[i+1] for i in waypoint_order] + [waypoint_names[-1]]

    stops_coords = []
    travel_times_min = []
    for leg in legs:
        stops_coords.append((leg['start_location']['lat'], leg['start_location']['lng']))
        travel_times_min.append(round(leg['duration']['value'] / 60))
    stops_coords.append((legs[-1]['end_location']['lat'], legs[-1]['end_location']['lng']))
    travel_times_min.append(0)

    route_map = folium.Map(location=stops_coords[0], zoom_start=15)

    for idx, leg in enumerate(legs):
        leg_path = []
        for step in leg['steps']:
            decoded = polyline.decode(step['polyline']['points'])
            leg_path.extend(decoded)
        folium.PolyLine(leg_path, color=colors[idx % len(colors)], weight=5).add_to(route_map)

    for idx, (coord, name, travel_min) in enumerate(zip(stops_coords, reordered_waypoint_names, travel_times_min)):
        if idx == 0:
            folium.Marker(coord, popup=f"Start: {name}", icon=folium.Icon(color='green', icon='play')).add_to(route_map)
        elif idx == len(stops_coords) - 1:
            folium.Marker(coord, popup=f"End: {name}", icon=folium.Icon(color='red', icon='flag')).add_to(route_map)
        else:
            folium.Marker(coord, popup=f"Stop {idx}: {name}\nTravel: {travel_min} min",
                          icon=BeautifyIcon(number=idx, border_color=colors[idx % len(colors)],
                                            text_color=colors[idx % len(colors)], background_color='white')).add_to(route_map)
    return route_map

# ====== MAIN STREAMLIT APP ======

def main():
    st.set_page_config(page_title="Google Maps Route Optimizer", page_icon="🗺️", layout="wide")
    st.title("🛤️ Google Maps Route Optimizer & Visualizer")

    with st.sidebar:
        st.header("🔗 Input Method")
        input_method = st.radio("Choose Input Method:", ["Manual Entry", "Paste Google Maps URL", "Import Excel/CSV"])
        default_subzone = st.text_input("Default Subzone:", value="Tampines")
        selected_modes = st.multiselect("Choose Transport Modes:", ["driving", "walking", "transit"], default=["driving"])
        if st.button("🚪 Exit App"):
            st.success("Exiting app... Goodbye! 👋")
            time.sleep(1)
            os._exit(0)

    stops_list = []

    if input_method == "Manual Entry":
        origin_input = st.text_input("Origin:")
        waypoints_input = st.text_area("Waypoints (one per line):")
        destination_input = st.text_input("Destination:")

        if st.button("Process Route"):
            if origin_input and destination_input:
                stops_list = [origin_input] + [line.strip() for line in waypoints_input.split("\n") if line.strip()] + [destination_input]
                st.session_state["stops_list"] = stops_list

    elif input_method == "Paste Google Maps URL":
        url_input = st.text_input("Paste Google Maps URL:")
        if st.button("Parse URL"):
            try:
                parsed_stops = parse_google_maps_url(url_input)
                st.session_state["stops_list"] = parsed_stops
                st.success("Parsed stops successfully.")
            except Exception as e:
                st.error(str(e))

    elif input_method == "Import Excel/CSV":
        uploaded_file = st.file_uploader("Upload Excel or CSV:", type=['csv', 'xlsx'])
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
                col = st.selectbox("Select column with addresses:", df.columns)
                stops_list = df[col].dropna().tolist()
                st.session_state["stops_list"] = stops_list
            except Exception as e:
                st.error(str(e))

    if "stops_list" in st.session_state and st.session_state["stops_list"]:
        stops_list = st.session_state["stops_list"]

        origin = st.selectbox("Select Origin:", stops_list)
        destination = st.selectbox("Select Destination:", stops_list)
        waypoints = st.multiselect("Select Waypoints (optional):", [s for s in stops_list if s not in [origin, destination]])

        if st.button("Optimize and Visualize Route"):
            try:
                origin_clean = clean_address_with_subzone(origin, default_subzone)
                destination_clean = clean_address_with_subzone(destination, default_subzone)
                waypoints_clean = [clean_address_with_subzone(wp, default_subzone) for wp in waypoints]

                all_names = [origin_clean] + waypoints_clean + [destination_clean]
                waypoint_names = [improve_place_name(name) for name in all_names]

                tabs = st.tabs([mode.capitalize() for mode in selected_modes])

                for mode, tab in zip(selected_modes, tabs):
                    with tab:
                        route_data = get_optimized_route(origin_clean, destination_clean, waypoints_clean, mode)
                        summary = summarize_route(route_data, waypoint_names)

                        st.subheader(f"🚗 {mode.capitalize()} Route Summary")
                        st.json(summary)

                        st.write("🗺️ Visualized Route:")
                        route_map = plot_route(route_data, waypoint_names)
                        folium_static(route_map)

                        navigation_link = build_google_maps_link(origin_clean, waypoints_clean, destination_clean, waypoint_order=route_data['routes'][0].get('waypoint_order', []))
                        st.write("📋 Copy your Google Maps Navigation Link:")
                        copy_to_clipboard_button(navigation_link)

            except Exception as e:
                st.error(str(e))

if __name__ == "__main__":
    main()