FROM varnish:stable-alpine

ENV VARNISH_LISTEN_PORT=8080 \
    VARNISH_VCL=default.vcl \
    VARNISH_STORAGE=malloc,256m

COPY . /etc/varnish/

EXPOSE 8080

CMD ["sh", "-c", "exec varnishd -F -a :${VARNISH_LISTEN_PORT} -f /etc/varnish/${VARNISH_VCL} -s ${VARNISH_STORAGE}"]
j