# ==============================================================================
# Dockerfile para Odoo 19 con soporte para Addons personalizados ERP/WMS/TMS
# ==============================================================================
FROM odoo:19.0


USER root


# Instalación de librerías Python para WMS/TMS e integraciones avanzadas
RUN pip3 install --no-cache-dir --break-system-packages \
    pandas \
    numpy \
    openpyxl \
    boto3 \
    requests \
    zeep \
    python-barcode \
    qrcode[pil] \
    xmltodict \
    xlsxwriter \
    cryptography \
    psycopg2-binary

# Estructura de directorios para configuración y addons personalizados
RUN mkdir -p /etc/odoo /mnt/extra-addons /var/lib/odoo \
    && chown -R odoo:odoo /etc/odoo /mnt/extra-addons /var/lib/odoo

# Copiar archivo de configuración base
COPY ./odoo.conf /etc/odoo/odoo.conf
RUN chown odoo:odoo /etc/odoo/odoo.conf

USER odoo

EXPOSE 8069 8072

ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
