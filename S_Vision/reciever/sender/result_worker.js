const { Worker } = require("bullmq");

const worker = new Worker(
    "survelliance.fire-smoke-queue",
    async (job) => {
        // console.log("FINAL RESULT");
        console.log(JSON.stringify(job.data, null, 2));
    },
    {
        connection: {
            host: "localhost",
            port: 6379
        }
    }
);

worker.on("ready", () => {
    console.log("Worker Ready");
});

worker.on("error", (err) => {
    console.error("Worker Error:", err);
});

worker.on("failed", (job, err) => {
    console.error("Job Failed:", err);
});