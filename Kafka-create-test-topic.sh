docker compose exec kafka \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --create \
  --if-not-exists \
  --topic taxi-m0-test \
  --partitions 1 \
  --replication-factor 1
