from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_events,
    aws_sqs as sqs,
)
from constructs import Construct

class SqlQueueStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Queue for SQL statements
        sql_queue = sqs.Queue(
            self, "SqlStatementsQueue",
            visibility_timeout=Duration.seconds(180),  # >= lambda timeout + buffer
            retention_period=Duration.days(4)
        )

        # Producer Lambda (posts SQL statements to SQS)
        producer_fn = _lambda.Function(
            self, "SqlProducerFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="producer.handler",
            code=_lambda.Code.from_asset("lambda/sql_producer"),
            timeout=Duration.seconds(10)
        )
        sql_queue.grant_send_messages(producer_fn)

        # Consumer Lambda (reads from SQS and commits to MySQL)
        consumer_fn = _lambda.Function(
            self, "SqlConsumerFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="consumer.handler",
            code=_lambda.Code.from_asset("lambda/sql_consumer"),
            timeout=Duration.seconds(120),
            # Optional: cap total concurrency for this function (across all triggers)
            # reserved_concurrent_executions=100,
        )

        # SQS event source: process 10 at a time, up to 100 batches in parallel
        consumer_fn.add_event_source(
            lambda_events.SqsEventSource(
                sql_queue,
                batch_size=10,                 # exactly what you asked
                max_concurrency=100,           # up to 100 parallel batches
                # Optional tuning:
                # max_batching_window=Duration.seconds(1),
                # report_batch_item_failures=True,
            )
        )