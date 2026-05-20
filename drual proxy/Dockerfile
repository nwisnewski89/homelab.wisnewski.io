
envsubst '${BACKEND_HOST} ${BACKEND_PORT}' \
  < /etc/varnish/default.vcl.template \
  > /tmp/default.vcl

exec varnishd -F -f /tmp/default.vcl -a :80