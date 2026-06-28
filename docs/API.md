# API Layer — C# .NET 10 Specification

> Claude Code: implement all files in `backend/` using this spec.
> Read `docs/ARCHITECTURE.md` first for the full data flow context.

---

## Project setup

```bash
dotnet new webapi -n NewsMarketAgent.Api --framework net10.0
cd NewsMarketAgent.Api
dotnet add package Npgsql                              # PostgreSQL driver
dotnet add package Dapper                              # lightweight ORM
dotnet add package RabbitMQ.Client                     # message queue
dotnet add package Microsoft.Extensions.Http           # IHttpClientFactory
dotnet add package Swashbuckle.AspNetCore              # Swagger UI
```

---

## File: `backend/Program.cs`

```csharp
using NewsMarketAgent.Api.Services;
using NewsMarketAgent.Api.Queue;
using NewsMarketAgent.Api.Scheduler;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddCors(o => o.AddDefaultPolicy(p =>
    p.WithOrigins("http://localhost:5173")
     .AllowAnyHeader()
     .AllowAnyMethod()));

// Services
builder.Services.AddScoped<ISignalService,        SignalService>();
builder.Services.AddScoped<IWatchlistService,     WatchlistService>();
builder.Services.AddScoped<INewsIngestionService, NewsIngestionService>();
builder.Services.AddScoped<IDigestService,        DigestService>();
builder.Services.AddSingleton<IQueuePublisher,    RabbitMqPublisher>();

// HTTP client for calling Python agent trigger endpoint
builder.Services.AddHttpClient("python-agent", c =>
{
    c.BaseAddress = new Uri(builder.Configuration["PythonAgent:BaseUrl"]
                            ?? "http://localhost:5001/");
    c.Timeout = TimeSpan.FromSeconds(10);
});

// Background scheduler
builder.Services.AddHostedService<DailyIngestJob>();

// Npgsql data source (pooled)
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

---

## File: `backend/Controllers/SignalsController.cs`

```csharp
using Microsoft.AspNetCore.Mvc;
using NewsMarketAgent.Api.Services;
using NewsMarketAgent.Api.Models;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/signals")]
public class SignalsController : ControllerBase
{
    private readonly ISignalService _signals;

    public SignalsController(ISignalService signals) => _signals = signals;

    // GET /api/signals?ticker=AAPL&limit=20&from=2024-01-01
    [HttpGet]
    public async Task<IActionResult> GetSignals(
        [FromQuery] string? ticker,
        [FromQuery] int     limit  = 20,
        [FromQuery] string? from   = null)
    {
        var signals = await _signals.GetAsync(ticker, limit, from);
        return Ok(signals);
    }

    // GET /api/signals/:id
    [HttpGet("{id:guid}")]
    public async Task<IActionResult> GetById(Guid id)
    {
        var signal = await _signals.GetByIdAsync(id);
        if (signal is null) return NotFound();
        return Ok(signal);
    }

    // POST /api/signals/callback  ← Python agent posts here
    [HttpPost("callback")]
    public async Task<IActionResult> Callback([FromBody] SignalCallbackDto dto)
    {
        await _signals.ProcessCallbackAsync(dto);
        return Ok();
    }
}
```

---

## File: `backend/Controllers/WatchlistController.cs`

```csharp
using Microsoft.AspNetCore.Mvc;
using NewsMarketAgent.Api.Services;
using NewsMarketAgent.Api.Models;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/watchlist")]
public class WatchlistController : ControllerBase
{
    private readonly IWatchlistService _watchlist;

    public WatchlistController(IWatchlistService watchlist) => _watchlist = watchlist;

    // GET /api/watchlist
    [HttpGet]
    public async Task<IActionResult> GetAll()
    {
        var items = await _watchlist.GetAllAsync();
        return Ok(items);
    }

    // POST /api/watchlist  body: { ticker, name }
    [HttpPost]
    public async Task<IActionResult> Add([FromBody] AddWatchlistItemDto dto)
    {
        if (string.IsNullOrWhiteSpace(dto.Ticker))
            return BadRequest(new { message = "Ticker is required." });

        dto.Ticker = dto.Ticker.ToUpperInvariant();
        await _watchlist.AddAsync(dto);
        return Ok(new { ticker = dto.Ticker });
    }

    // DELETE /api/watchlist/:ticker
    [HttpDelete("{ticker}")]
    public async Task<IActionResult> Remove(string ticker)
    {
        await _watchlist.RemoveAsync(ticker.ToUpperInvariant());
        return NoContent();
    }
}
```

---

## File: `backend/Controllers/IngestController.cs`

```csharp
using Microsoft.AspNetCore.Mvc;
using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/ingest")]
public class IngestController : ControllerBase
{
    private readonly INewsIngestionService _ingest;

    public IngestController(INewsIngestionService ingest) => _ingest = ingest;

    // POST /api/ingest/trigger  — dev/manual trigger only
    // Delegates to Python agent (http://localhost:5001/trigger)
    // Python fetches news via yfinance and runs the full pipeline
    [HttpPost("trigger")]
    public async Task<IActionResult> Trigger()
    {
        var status = await _ingest.IngestLatestAsync();
        return Ok(new { status });
    }
}
```

---

## File: `backend/Controllers/PricesController.cs`

> Added in Phase 2 to serve the `SentimentChart` in the React frontend.

```csharp
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using NewsMarketAgent.Api.Data;
using NewsMarketAgent.Api.Models;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/prices")]
public class PricesController(AppDbContext db) : ControllerBase
{
    // GET /api/prices/{ticker}?days=30
    [HttpGet("{ticker}")]
    public async Task<IEnumerable<PriceResponseDto>> Get(string ticker, [FromQuery] int days = 30)
    {
        var cutoff = DateOnly.FromDateTime(DateTime.UtcNow.AddDays(-days));

        return await db.Prices
            .Where(p => p.Ticker == ticker.ToUpper() && p.Date >= cutoff)
            .OrderBy(p => p.Date)
            .Select(p => new PriceResponseDto
            {
                Ticker = p.Ticker,
                Date   = p.Date.ToString("yyyy-MM-dd"),
                Close  = p.Close,
            })
            .ToListAsync();
    }
}
```

Response shape (`PriceResponseDto`):

```json
[
  { "ticker": "AAPL", "date": "2024-01-15", "close": 185.92 },
  { "ticker": "AAPL", "date": "2024-01-16", "close": 183.63 }
]
```

---

## File: `backend/Controllers/BacktestController.cs`

```csharp
using Microsoft.AspNetCore.Mvc;
using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/backtest")]
public class BacktestController : ControllerBase
{
    private readonly ISignalService _signals;

    public BacktestController(ISignalService signals) => _signals = signals;

    // GET /api/backtest/:ticker  — Phase 3
    [HttpGet("{ticker}")]
    public async Task<IActionResult> GetBacktest(string ticker)
    {
        var result = await _signals.GetBacktestAsync(ticker.ToUpperInvariant());
        if (result is null) return NotFound(new { message = "No backtest data yet." });
        return Ok(result);
    }
}
```

---

## File: `backend/Models/Signal.cs`

```csharp
namespace NewsMarketAgent.Api.Models;

public class Signal
{
    public Guid     Id                    { get; set; } = Guid.NewGuid();
    public string   Ticker                { get; set; } = "";
    public Guid?    ArticleId             { get; set; }
    public string   EventType             { get; set; } = "";
    public string   Sentiment             { get; set; } = "";
    public decimal  Confidence            { get; set; }
    public string   ImpactSummary         { get; set; } = "";
    public string   TimeHorizon           { get; set; } = "";
    public string[] SourceCitations       { get; set; } = [];
    public string[] UncertaintyFactors    { get; set; } = [];
    public string   Disclaimer            { get; set; } = "";
    public bool     GovernancePassed      { get; set; }
    public int      SourceCredibilityTier { get; set; }
    public bool     AlertSuppressed       { get; set; }
    public bool     RequiresHumanReview   { get; set; }
    public string[] GovernanceWarnings    { get; set; } = [];
    public DateTime PublishedAt           { get; set; }
    public DateTime CreatedAt             { get; set; } = DateTime.UtcNow;
}

// Shape returned to React — never return raw Signal without governance check
public class SignalResponseDto
{
    public string   Id                    { get; set; } = "";
    public string   Ticker                { get; set; } = "";
    public string   EventType             { get; set; } = "";
    public string   Sentiment             { get; set; } = "";
    public decimal  Confidence            { get; set; }
    public string   ImpactSummary         { get; set; } = "";
    public string   TimeHorizon           { get; set; } = "";
    public string[] SourceCitations       { get; set; } = [];
    public string[] UncertaintyFactors    { get; set; } = [];
    public string   Disclaimer            { get; set; } = "";
    public DateTime PublishedAt           { get; set; }
    public bool     GovernancePassed      { get; set; }
    public int      SourceCredibilityTier { get; set; }
    public string[] GovernanceWarnings    { get; set; } = [];
}
```

---

## File: `backend/Models/NewsArticle.cs`

```csharp
namespace NewsMarketAgent.Api.Models;

public class NewsArticle
{
    public Guid     Id          { get; set; } = Guid.NewGuid();
    public string   Ticker      { get; set; } = "";
    public string   Headline    { get; set; } = "";
    public string?  Body        { get; set; }
    public string?  SourceUrl   { get; set; }
    public string?  SourceName  { get; set; }
    public string?  FinnhubId   { get; set; }   // dedup key
    public DateTime PublishedAt { get; set; }
    public DateTime IngestedAt  { get; set; } = DateTime.UtcNow;
    public bool     Processed   { get; set; }
}
```

---

## File: `backend/Models/WatchlistItem.cs`

```csharp
namespace NewsMarketAgent.Api.Models;

public class WatchlistItem
{
    public string   Ticker  { get; set; } = "";
    public string?  Name    { get; set; }
    public DateTime AddedAt { get; set; } = DateTime.UtcNow;
}

public class AddWatchlistItemDto
{
    public string  Ticker { get; set; } = "";
    public string? Name   { get; set; }
}
```

---

## File: `backend/Models/SignalCallbackDto.cs`

```csharp
namespace NewsMarketAgent.Api.Models;

public class SignalCallbackDto
{
    public Guid    ArticleId        { get; set; }
    public string  Ticker           { get; set; } = "";
    public bool    GovernancePassed { get; set; }
    public string? RejectionReason  { get; set; }
    public SignalPayloadDto? Signal { get; set; }
}

public class SignalPayloadDto
{
    public string   EventType             { get; set; } = "";
    public string   Sentiment             { get; set; } = "";
    public decimal  Confidence            { get; set; }
    public string   ImpactSummary         { get; set; } = "";
    public string   TimeHorizon           { get; set; } = "";
    public string[] SourceCitations       { get; set; } = [];
    public string[] UncertaintyFactors    { get; set; } = [];
    public string   Disclaimer            { get; set; } = "";
    public int      SourceCredibilityTier { get; set; }
    public string[] GovernanceWarnings    { get; set; } = [];
    public bool     AlertSuppressed       { get; set; }
    public bool     RequiresHumanReview   { get; set; }
}
```

---

## File: `backend/Services/NewsIngestionService.cs`

News fetching is handled entirely by the Python agent (via yfinance — free, no key).
C# just triggers the Python side; it does not call any external news API.

```csharp
namespace NewsMarketAgent.Api.Services;

public interface INewsIngestionService
{
    Task<string> IngestLatestAsync();
}

public class NewsIngestionService : INewsIngestionService
{
    private readonly IHttpClientFactory              _http;
    private readonly ILogger<NewsIngestionService>   _log;

    public NewsIngestionService(IHttpClientFactory http,
                                ILogger<NewsIngestionService> log)
    {
        _http = http;
        _log  = log;
    }

    public async Task<string> IngestLatestAsync()
    {
        // Delegates to Python agent which fetches news via yfinance (free, no key)
        // Python runs the full pipeline and callbacks results via /api/signals/callback
        var client = _http.CreateClient("python-agent");

        try
        {
            var resp = await client.PostAsync("/trigger", null);

            if (resp.IsSuccessStatusCode)
            {
                _log.LogInformation("Ingest triggered on Python agent");
                return "triggered";
            }

            _log.LogWarning("Python agent trigger returned {Status}", resp.StatusCode);
            return "python_agent_error";
        }
        catch (HttpRequestException ex)
        {
            _log.LogError(ex, "Could not reach Python agent at {Base}",
                          client.BaseAddress);
            return "python_agent_unreachable";
        }
    }
}
```

---

## File: `backend/Services/SignalService.cs`

```csharp
using Dapper;
using Npgsql;
using NewsMarketAgent.Api.Models;

namespace NewsMarketAgent.Api.Services;

public interface ISignalService
{
    Task<IEnumerable<SignalResponseDto>> GetAsync(string? ticker, int limit, string? from);
    Task<SignalResponseDto?>             GetByIdAsync(Guid id);
    Task                                 ProcessCallbackAsync(SignalCallbackDto dto);
    Task<object?>                        GetBacktestAsync(string ticker);
}

public class SignalService : ISignalService
{
    private readonly NpgsqlDataSource _db;

    public SignalService(NpgsqlDataSource db) => _db = db;

    public async Task<IEnumerable<SignalResponseDto>> GetAsync(
        string? ticker, int limit, string? from)
    {
        await using var conn = await _db.OpenConnectionAsync();

        var sql = """
            SELECT id, ticker, event_type, sentiment, confidence, impact_summary,
                   time_horizon, source_citations, uncertainty_factors, disclaimer,
                   published_at, governance_passed, source_credibility_tier,
                   governance_warnings
            FROM signals
            WHERE governance_passed = true
            """;

        var conditions = new List<string>();
        var p = new DynamicParameters();

        if (!string.IsNullOrEmpty(ticker)) { conditions.Add("AND ticker = @Ticker"); p.Add("Ticker", ticker); }
        if (!string.IsNullOrEmpty(from))   { conditions.Add("AND published_at >= @From"); p.Add("From", from); }

        sql += string.Join(" ", conditions) + " ORDER BY published_at DESC LIMIT @Limit";
        p.Add("Limit", limit);

        return await conn.QueryAsync<SignalResponseDto>(sql, p);
    }

    public async Task<SignalResponseDto?> GetByIdAsync(Guid id)
    {
        await using var conn = await _db.OpenConnectionAsync();
        return await conn.QuerySingleOrDefaultAsync<SignalResponseDto>(
            "SELECT * FROM signals WHERE id = @Id AND governance_passed = true",
            new { Id = id });
    }

    public async Task ProcessCallbackAsync(SignalCallbackDto dto)
    {
        await using var conn = await _db.OpenConnectionAsync();

        // Mark article as processed
        await conn.ExecuteAsync(
            "UPDATE news_articles SET processed = true WHERE id = @Id",
            new { Id = dto.ArticleId });

        if (!dto.GovernancePassed || dto.Signal is null) return;

        // Apply C#-side governance double-check
        if (!PassesApiGovernance(dto.Signal)) return;

        await conn.ExecuteAsync("""
            INSERT INTO signals
                (ticker, article_id, event_type, sentiment, confidence, impact_summary,
                 time_horizon, source_citations, uncertainty_factors, disclaimer,
                 governance_passed, source_credibility_tier, alert_suppressed,
                 requires_human_review, governance_warnings, published_at)
            VALUES
                (@Ticker, @ArticleId, @EventType, @Sentiment, @Confidence, @ImpactSummary,
                 @TimeHorizon, @SourceCitations, @UncertaintyFactors, @Disclaimer,
                 true, @SourceCredibilityTier, @AlertSuppressed,
                 @RequiresHumanReview, @GovernanceWarnings, NOW())
            """,
            new
            {
                dto.Ticker, ArticleId = dto.ArticleId,
                dto.Signal.EventType, dto.Signal.Sentiment, dto.Signal.Confidence,
                dto.Signal.ImpactSummary, dto.Signal.TimeHorizon,
                dto.Signal.SourceCitations, dto.Signal.UncertaintyFactors,
                dto.Signal.Disclaimer, dto.Signal.SourceCredibilityTier,
                dto.Signal.AlertSuppressed, dto.Signal.RequiresHumanReview,
                dto.Signal.GovernanceWarnings,
            });
    }

    public async Task<object?> GetBacktestAsync(string ticker)
    {
        await using var conn = await _db.OpenConnectionAsync();
        return await conn.QuerySingleOrDefaultAsync<object>(
            "SELECT * FROM backtest_results WHERE ticker = @Ticker ORDER BY computed_at DESC LIMIT 1",
            new { Ticker = ticker });
    }

    private static bool PassesApiGovernance(SignalPayloadDto s)
    {
        if (string.IsNullOrEmpty(s.Disclaimer)) return false;
        if (s.Confidence < 0.65m) return false;
        var prohibited = new[] { "buy", "sell", "invest", "guaranteed", "price target" };
        return !prohibited.Any(p =>
            s.ImpactSummary?.Contains(p, StringComparison.OrdinalIgnoreCase) ?? false);
    }
}
```

---

## File: `backend/Queue/RabbitMqPublisher.cs`

```csharp
using RabbitMQ.Client;
using System.Text;
using System.Text.Json;

namespace NewsMarketAgent.Api.Queue;

public record IngestJobMessage
{
    public Guid     ArticleId   { get; init; }
    public string   Ticker      { get; init; } = "";
    public string   Headline    { get; init; } = "";
    public string   Body        { get; init; } = "";
    public string   SourceUrl   { get; init; } = "";
    public string   SourceName  { get; init; } = "";
    public DateTime PublishedAt { get; init; }
}

public interface IQueuePublisher
{
    Task PublishAsync(IngestJobMessage message);
}

public class RabbitMqPublisher : IQueuePublisher, IDisposable
{
    private readonly IConnection _connection;
    private readonly IModel      _channel;
    private readonly string      _queue;

    public RabbitMqPublisher(IConfiguration config)
    {
        var host = config["RabbitMq:Host"] ?? "localhost";
        _queue   = config["RabbitMq:Queue"] ?? "news_analysis_jobs";

        var factory = new ConnectionFactory { HostName = host };
        _connection = factory.CreateConnection();
        _channel    = _connection.CreateModel();

        _channel.QueueDeclare(queue: _queue, durable: true,
                              exclusive: false, autoDelete: false);
    }

    public Task PublishAsync(IngestJobMessage message)
    {
        var body  = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(message));
        var props = _channel.CreateBasicProperties();
        props.Persistent = true;

        _channel.BasicPublish(exchange: "", routingKey: _queue,
                              basicProperties: props, body: body);
        return Task.CompletedTask;
    }

    public void Dispose() { _channel?.Dispose(); _connection?.Dispose(); }
}
```

---

## File: `backend/Scheduler/DailyIngestJob.cs`

```csharp
using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Scheduler;

public class DailyIngestJob : BackgroundService
{
    private readonly IServiceProvider _services;
    private readonly IConfiguration   _config;
    private readonly ILogger<DailyIngestJob> _log;

    public DailyIngestJob(IServiceProvider services, IConfiguration config,
                          ILogger<DailyIngestJob> log)
    {
        _services = services;
        _config   = config;
        _log      = log;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            var now     = DateTime.Now;
            var trigger = TimeOnly.Parse(_config["Scheduler:DailyIngestTime"] ?? "07:00");
            var next    = now.Date.Add(trigger.ToTimeSpan());
            if (next <= now) next = next.AddDays(1);

            // Skip weekends
            while (next.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday)
                next = next.AddDays(1);

            var delay = next - now;
            _log.LogInformation("Next ingest scheduled for {Next}", next);

            await Task.Delay(delay, stoppingToken);

            try
            {
                using var scope   = _services.CreateScope();
                var ingest        = scope.ServiceProvider.GetRequiredService<INewsIngestionService>();
                var count         = await ingest.IngestLatestAsync();
                _log.LogInformation("Scheduled ingest complete — {Count} articles queued", count);
            }
            catch (Exception ex)
            {
                _log.LogError(ex, "Scheduled ingest failed");
            }
        }
    }
}
```

---

## File: `backend/appsettings.Development.json`

```json
{
  "ConnectionStrings": {
    "Postgres": "Host=localhost;Database=news_market;Username=postgres;Password=postgres"
  },
  "RabbitMq": {
    "Host":  "localhost",
    "Queue": "news_analysis_jobs"
  },
  "PythonAgent": {
    "BaseUrl":     "http://localhost:5001",
    "CallbackUrl": "http://localhost:5000/api/signals/callback"
  },
  "Scheduler": {
    "DailyIngestTime": "07:00"
  },
  "Watchlist": {
    "DefaultTickers": "AAPL,MSFT,TSLA,SPY,QQQ"
  },
  "Logging": {
    "LogLevel": {
      "Default":              "Information",
      "Microsoft.AspNetCore": "Warning"
    }
  }
}
```

---

## Claude Code instructions for this layer

1. Seed the `watchlist` table on startup if empty using `Watchlist:DefaultTickers` config
2. The callback endpoint (`POST /api/signals/callback`) must not be CORS-restricted —
   it is called by the Python agent on the same host, not by the browser
3. All `SignalResponseDto` items returned to React must have `governancePassed = true` —
   filter at the DB query level, not in application code
4. `DigestService` assembles the daily digest by grouping signals by ticker and event type;
   see `GET /api/digest/latest` endpoint (add to SignalsController or a dedicated controller)
5. Run `docker-compose up -d` first to start PostgreSQL and RabbitMQ before `dotnet run`
