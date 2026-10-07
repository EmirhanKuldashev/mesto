# Independent road graph: no POI snapshot, public routing demo, or runtime fetch.
FROM ghcr.io/project-osrm/osrm-backend:v5.27.1@sha256:855614a38f464b0558a2ad6eaa7cb8c139f39887da9b38b485ce453c6e6e6124 AS graph
WORKDIR /data
COPY data/fixtures/routing/krasnoyarsk-car-v1.osm.pbf ./
RUN echo 'b628177781f0161e63fce958672bd5c384f0119bccd420828425e17c985d642f  krasnoyarsk-car-v1.osm.pbf' | sha256sum -c - \
    && echo 'cb3df0546318665609606b746a1297f3d65ca3c2ff825f8a6f3c57247d86a2d3  /opt/car.lua' | sha256sum -c - \
    && osrm-extract --threads 2 --profile /opt/car.lua --data_version mesto-car-v1-b628177781f0161e63fce958672bd5c384f0119bccd420828425e17c985d642f krasnoyarsk-car-v1.osm.pbf \
    && osrm-partition --threads 2 krasnoyarsk-car-v1.osrm \
    && osrm-customize --threads 2 krasnoyarsk-car-v1.osrm

FROM ghcr.io/project-osrm/osrm-backend:v5.27.1@sha256:855614a38f464b0558a2ad6eaa7cb8c139f39887da9b38b485ce453c6e6e6124
WORKDIR /data
COPY --from=graph /data/*.osrm* ./
COPY data/routing/healthcheck.sh /opt/mesto-healthcheck.sh
RUN sed -i 's/\r$//' /opt/mesto-healthcheck.sh && chmod +x /opt/mesto-healthcheck.sh
EXPOSE 5000
CMD ["osrm-routed", "--algorithm", "mld", "--threads", "2", "/data/krasnoyarsk-car-v1.osrm"]
