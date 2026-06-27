# API Layer — C# .NET 10 Specification

> Claude Code: implement all files in `backend/` using this spec.
> Read `docs/ARCHITECTURE.md` first for the full data flow context.

## Project setup

```bash
dotnet new webapi -n EtlAgent.Api --framework net10.0
cd EtlAgent.Api
dotnet add package Npgsql.EntityFrameworkCore.PostgreSQL
dotnet add package RabbitMQ.Client
dotnet add package StackExchange.Redis          # if using Redis instead of RabbitMQ
dotnet add package Microsoft.AspNetCore.Http.Features  # large file uploads
```

## File: `backend/Program.cs`

```csharp
using EtlAgent.Api.Services;
using EtlAgent.Api.Queue;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

// CORS — allow React dev server
builder.Services.AddCors(o => o.AddDefaultPolicy(p =>
    p.WithOrigins("http://localhost:5173")
     .AllowAnyHeader()
     .AllowAnyMethod()));

// Configure large file uploads (50 MB)
builder.Services.Configure<FormOptions>(o => {
    o.MultipartBodyLengthLimit = 52_428_800; // 50 MB
});

// DI registrations
builder.Services.AddScoped<IFileIngestionService, FileIngestionService>();
builder.Services.AddScoped<IJobStatusService, JobStatusService>();
builder.Services.AddSingleton<IQueuePublisher, RabbitMqPublisher>();

// PostgreSQL via EF Core (or use Dapper — your choice)
builder.Services.AddNpgsqlDataSource(
    builder.Configuration.GetConnectionString("Postgres")!);

var app = builder.Build();

app.UseCors();
app.UseSwagger();
app.UseSwaggerUI();
app.UseAuthorization();
app.MapControllers();
app.Run();
```

## File: `backend/Controllers/EtlController.cs`

Implement these three endpoints exactly as specified. The React frontend depends on
this contract — do not change field names.

```csharp
using Microsoft.AspNetCore.Mvc;
using EtlAgent.Api.Services;
using EtlAgent.Api.Models;

namespace EtlAgent.Api.Controllers;

[ApiController]
[Route("api/etl")]
public class EtlController : ControllerBase
{
    private readonly IFileIngestionService _ingestion;
    private readonly IJobStatusService _status;

    public EtlController(IFileIngestionService ingestion, IJobStatusService status)
    {
        _ingestion = ingestion;
        _status    = status;
    }

    // ── POST /api/etl/upload ───────────────────────────────────────────
    // Body: multipart/form-data { file: <binary> }
    // Returns: 200 { jobId: "uuid" }  |  400 { message: "..." }
    [HttpPost("upload")]
    [RequestSizeLimit(52_428_800)]
    public async Task<IActionResult> Upload(IFormFile file)
    {
        // Validation
        if (file is null || file.Length == 0)
            return BadRequest(new { message = "No file provided." });

        var allowed = new[] { ".csv", ".xlsx", ".xls" };
        var ext = Path.GetExtension(file.FileName).ToLowerInvariant();
        if (!allowed.Contains(ext))
            return BadRequest(new { message = "Only .csv, .xlsx, and .xls files are supported." });

        if (file.Length > 52_428_800)
            return BadRequest(new { message = "File exceeds 50 MB limit." });

        var jobId = await _ingestion.IngestAsync(file);
        return Ok(new { jobId });
    }

    // ── GET /api/etl/status/:jobId ─────────────────────────────────────
    // Returns job record + per-step agent status
    [HttpGet("status/{jobId:guid}")]
    public async Task<IActionResult> Status(Guid jobId)
    {
        var job = await _status.GetAsync(jobId);
        if (job is null) return NotFound(new { message = "Job not found." });
        return Ok(job);
    }

    // ── POST /api/etl/callback ─────────────────────────────────────────
    // Called by the Python agent service to report step progress.
    // Not exposed to the browser — internal use only.
    [HttpPost("callback")]
    public async Task<IActionResult> Callback([FromBody] AgentCallbackDto dto)
    {
        await _status.UpdateStepAsync(dto);
        return Ok();
    }
}
```

## File: `backend/Models/UploadJob.cs`

```csharp
namespace EtlAgent.Api.Models;

public class UploadJob
{
    public Guid   Id        { get; set; } = Guid.NewGuid();
    public string Status    { get; set; } = "queued"; // queued|processing|completed|failed
    public string FileName  { get; set; } = "";
    public string FilePath  { get; set; } = "";
    public string? Summary  { get; set; }
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; set; } = DateTime.UtcNow;
}

// The shape returned to the React frontend
public class JobStatusDto
{
    public Guid   JobId      { get; set; }
    public string Status     { get; set; } = "";
    public AgentStepsDto AgentSteps { get; set; } = new();
    public string? Summary   { get; set; }
}

public class AgentStepsDto
{
    public string Schema    { get; set; } = "pending";
    public string Classify  { get; set; } = "pending";
    public string Transform { get; set; } = "pending";
    public string Load      { get; set; } = "pending";
}

// Callback payload from Python agent
public class AgentCallbackDto
{
    public Guid   JobId   { get; set; }
    public string Step    { get; set; } = "";   // schema|classify|transform|load
    public string Status  { get; set; } = "";   // running|done|failed
    public object? Payload { get; set; }
    public string? Error  { get; set; }
    public bool   IsJobComplete { get; set; }   // true on final step
}
```

## File: `backend/Services/FileIngestionService.cs`

```csharp
using EtlAgent.Api.Models;
using EtlAgent.Api.Queue;

namespace EtlAgent.Api.Services;

public interface IFileIngestionService
{
    Task<Guid> IngestAsync(IFormFile file);
}

public class FileIngestionService : IFileIngestionService
{
    private readonly IQueuePublisher _queue;
    private readonly IConfiguration  _config;
    private readonly ILogger<FileIngestionService> _logger;

    // Upload root — configure in appsettings.json: "UploadPath": "/var/uploads"
    private string UploadRoot => _config["UploadPath"] ?? Path.Combine(Path.GetTempPath(), "etl-uploads");

    public FileIngestionService(IQueuePublisher queue, IConfiguration config,
                                ILogger<FileIngestionService> logger)
    {
        _queue  = queue;
        _config = config;
        _logger = logger;
    }

    public async Task<Guid> IngestAsync(IFormFile file)
    {
        var jobId   = Guid.NewGuid();
        var ext     = Path.GetExtension(file.FileName);
        var destDir = Path.Combine(UploadRoot, jobId.ToString());
        Directory.CreateDirectory(destDir);

        var destPath = Path.Combine(destDir, $"upload{ext}");

        // Save file to disk
        await using var stream = File.Create(destPath);
        await file.CopyToAsync(stream);

        // TODO: Insert job record into PostgreSQL here
        // await _db.ExecuteAsync(
        //   "INSERT INTO jobs (id, status, file_name, file_path) VALUES (@id, 'queued', @name, @path)",
        //   new { id = jobId, name = file.FileName, path = destPath });

        // Publish to queue
        await _queue.PublishAsync(new QueueMessage
        {
            JobId    = jobId,
            FilePath = destPath,
            FileName = file.FileName,
            FileType = ext.TrimStart('.').ToLower()
        });

        _logger.LogInformation("Job {JobId} queued for file {FileName}", jobId, file.FileName);
        return jobId;
    }
}
```

## File: `backend/Services/JobStatusService.cs`

```csharp
using EtlAgent.Api.Models;

namespace EtlAgent.Api.Services;

public interface IJobStatusService
{
    Task<JobStatusDto?> GetAsync(Guid jobId);
    Task UpdateStepAsync(AgentCallbackDto dto);
}

public class JobStatusService : IJobStatusService
{
    // TODO: inject NpgsqlDataSource or DbContext
    // All queries are placeholders — implement with your chosen DB library

    public async Task<JobStatusDto?> GetAsync(Guid jobId)
    {
        // TODO: Query jobs + agent_steps tables
        // SELECT * FROM jobs WHERE id = @jobId
        // SELECT step, status FROM agent_steps WHERE job_id = @jobId

        // Placeholder until DB is wired up:
        await Task.CompletedTask;
        return new JobStatusDto
        {
            JobId  = jobId,
            Status = "processing",
            AgentSteps = new AgentStepsDto
            {
                Schema    = "done",
                Classify  = "running",
                Transform = "pending",
                Load      = "pending"
            }
        };
    }

    public async Task UpdateStepAsync(AgentCallbackDto dto)
    {
        // TODO:
        // 1. UPSERT agent_steps row for (job_id, step)
        // 2. If dto.IsJobComplete == true, UPDATE jobs SET status = dto.Status
        // 3. If dto.Status == "failed", UPDATE jobs SET status = 'failed'

        await Task.CompletedTask;
    }
}
```

## File: `backend/Queue/RabbitMqPublisher.cs`

```csharp
using RabbitMQ.Client;
using System.Text;
using System.Text.Json;
using EtlAgent.Api.Models;

namespace EtlAgent.Api.Queue;

public record QueueMessage
{
    public Guid   JobId    { get; init; }
    public string FilePath { get; init; } = "";
    public string FileName { get; init; } = "";
    public string FileType { get; init; } = "";
}

public interface IQueuePublisher
{
    Task PublishAsync(QueueMessage message);
}

public class RabbitMqPublisher : IQueuePublisher, IDisposable
{
    private readonly IConnection _connection;
    private readonly IModel      _channel;
    private readonly string      _queue;

    public RabbitMqPublisher(IConfiguration config)
    {
        var host  = config["RabbitMq:Host"]  ?? "localhost";
        _queue    = config["RabbitMq:Queue"] ?? "etl_jobs";

        var factory = new ConnectionFactory { HostName = host };
        _connection = factory.CreateConnection();
        _channel    = _connection.CreateModel();

        _channel.QueueDeclare(
            queue:      _queue,
            durable:    true,    // survives broker restart
            exclusive:  false,
            autoDelete: false,
            arguments:  null);
    }

    public Task PublishAsync(QueueMessage message)
    {
        var body  = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(message));
        var props = _channel.CreateBasicProperties();
        props.Persistent = true;   // survive broker restart

        _channel.BasicPublish(
            exchange:   "",
            routingKey: _queue,
            basicProperties: props,
            body:       body);

        return Task.CompletedTask;
    }

    public void Dispose()
    {
        _channel?.Dispose();
        _connection?.Dispose();
    }
}
```

## File: `backend/appsettings.Development.json`

```json
{
  "ConnectionStrings": {
    "Postgres": "Host=localhost;Database=etl_agent;Username=postgres;Password=postgres"
  },
  "RabbitMq": {
    "Host":  "localhost",
    "Queue": "etl_jobs"
  },
  "UploadPath": "/tmp/etl-uploads",
  "PythonAgent": {
    "CallbackUrl": "http://localhost:5000/api/etl/callback"
  },
  "Logging": {
    "LogLevel": {
      "Default":              "Information",
      "Microsoft.AspNetCore": "Warning"
    }
  }
}
```

## Claude Code instructions for this layer

When implementing the backend:

1. Wire up Npgsql for real DB queries in `JobStatusService` and `FileIngestionService`
2. Create EF Core migrations OR raw SQL init script matching the schema in `ARCHITECTURE.md`
3. Replace placeholder DB calls with real async Npgsql queries
4. Add `docker-compose.yml` at the repo root with postgres + rabbitmq services
5. Add integration tests for the upload and status endpoints

Command to scaffold and run:
```bash
cd backend
dotnet restore
dotnet ef migrations add InitialCreate   # if using EF Core
dotnet run
# Swagger UI available at http://localhost:5000/swagger
```
