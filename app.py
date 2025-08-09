import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Point
import pydeck as pdk
import geodatasets

st.set_page_config(page_title="GeoPandas + Streamlit Mini Demo", layout="wide")
st.title("GeoPandas + Streamlit: Minimal Spatial Analytics Demo")

st.markdown(
    """
    This demo uses **GeoPandas** to do a basic spatial workflow and **Streamlit** to show
    an interactive map via **pydeck** (deck.gl). It runs on the Natural Earth dataset
    shipped with GeoPandas (no internet required).
    """
)

@st.cache_data
def load_data():
    # countries = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    
    NAT_EARTH_URL = "https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip"
    #NAT_EARTH_URL = "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"
    countries = gpd.read_file(NAT_EARTH_URL).to_crs(4326)

    # standardise the name column
    for c in ["name", "ADMIN", "NAME", "NAME_LONG", "admin", "name_long"]:
        if c in countries.columns:
            countries = countries.rename(columns={c: "name"})
            break

    # drop Antarctica if present
    if "name" in countries.columns:
        countries = countries[countries["name"].str.lower() != "antarctica"].reset_index(drop=True)

    

    rng = np.random.default_rng(42)
    lats = rng.uniform(low=-60, high=75, size=600)
    lons = rng.uniform(low=-180, high=180, size=600)
    pts = gpd.GeoDataFrame(
        {"id": np.arange(lats.size), "lat": lats, "lon": lons},
        geometry=[Point(xy) for xy in zip(lons, lats)],
        crs="EPSG:4326",
    )
    return countries, pts

countries, pts = load_data()

def view_from_bounds(gdf):
    minx, miny, maxx, maxy = gdf.total_bounds
    center_lat = (miny + maxy) / 2
    center_lon = (minx + maxx) / 2
    # 粗略把经纬度跨度映射到 WebMercator 缩放级别
    span = max(maxx - minx, maxy - miny, 0.1)  # 防 0
    zoom = float(np.clip(np.log2(360.0 / span), 2, 8))  # 2~8 之间
    return center_lat, center_lon, zoom

with st.sidebar:
    st.header("Controls")
    options = sorted(countries["name"].unique())
    default_idx = options.index("New Zealand") if "New Zealand" in options else 0
    country_name = st.selectbox("Country:", options=options, index=default_idx)
    buffer_km = st.slider("Buffer distance (km)", 0, 200, 50, step=10)
    show_all_countries = st.checkbox("Show all country boundaries", value=True)
    show_points_outside = st.checkbox("Show points outside country", value=False)

sel = countries[countries["name"] == country_name]
if sel.empty:
    st.stop()
sel = sel.copy()
sel["geometry"] = sel.geometry.buffer(0)
sel = sel.explode(index_parts=False, ignore_index=True)

# Buffer in meters using a metric CRS (Web Mercator for simplicity)
sel_3857 = sel.to_crs(3857)
buffered_3857 = sel_3857.buffer(buffer_km * 1000)
buffered = gpd.GeoDataFrame(geometry=buffered_3857, crs=3857).to_crs(4326)

# Spatial join: points inside the selected country
joined = gpd.sjoin(pts, sel[["name", "geometry"]], predicate="within", how="left")
joined["inside"] = joined["name"].notna()

inside_pts = joined[joined["inside"]][["lat", "lon", "id"]].copy()
outside_pts = joined[~joined["inside"]][["lat", "lon", "id"]].copy()

rep = sel.geometry.representative_point().iloc[0]
center_lat, center_lon = rep.y, rep.x

c1, c2, c3 = st.columns(3)
c1.metric("Points inside", f"{int(joined['inside'].sum())}")
c2.metric("Total points", f"{int(len(joined))}")
c3.metric("Buffer (km)", f"{buffer_km}")

layers = []
if show_all_countries:
    layers.append(pdk.Layer("GeoJsonLayer", data=countries.__geo_interface__,
                            stroked=True, filled=False,
                            get_line_color=[100,100,100,120], line_width_min_pixels=1,wrapLongitude=True))

layers.append(pdk.Layer("GeoJsonLayer", data=sel.__geo_interface__,
                        stroked=True, filled=True,
                        get_fill_color=[30,144,255,60],
                        get_line_color=[30,144,255,200], line_width_min_pixels=2,wrapLongitude=True))

if buffer_km > 0:
    layers.append(pdk.Layer("GeoJsonLayer", data=buffered.__geo_interface__,
                            stroked=True, filled=False,
                            get_line_color=[255,140,0,180], line_width_min_pixels=2,wrapLongitude=True))

if len(inside_pts) > 0:
    layers.append(pdk.Layer("ScatterplotLayer", data=inside_pts,
                            get_position='[lon, lat]',
                            get_radius=20000, radius_units="meters",
                            get_fill_color=[0,122,255,180], pickable=True))

if show_points_outside and len(outside_pts) > 0:
    layers.append(pdk.Layer("ScatterplotLayer", data=outside_pts,
                            get_position='[lon, lat]',
                            get_radius=15000, radius_units="meters",
                            get_fill_color=[120,120,120,120], pickable=True))

# view_state = pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=3)
clat, clon, z = view_from_bounds(sel)
view_state = pdk.ViewState(latitude=clat, longitude=clon, zoom=z)
st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view_state, map_style=None))

with st.expander("Under the hood"):
    st.markdown(
        """
        - Load countries with **GeoPandas** (Natural Earth sample).
        - Compute a **buffer** in a metric CRS (EPSG:3857) and project back to EPSG:4326.
        - **sjoin** to flag which random points fall inside the country polygon.
        - Visualise with **pydeck**; download the joined table as CSV.
        """
    )
    csv = joined.drop(columns=["geometry"]).to_csv(index=False).encode("utf-8")
    st.download_button("Download joined points (CSV)",
                       data=csv, file_name="joined_points.csv", mime="text/csv")

st.caption("Tip: tweak the country and buffer in the sidebar.")