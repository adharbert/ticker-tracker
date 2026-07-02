using Microsoft.EntityFrameworkCore;
using NewsMarketAgent.Api.Data;
using NewsMarketAgent.Api.Scheduler;
using NewsMarketAgent.Api.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddCors(o => o.AddDefaultPolicy(p =>
    p.WithOrigins("http://localhost:5173")
     .AllowAnyHeader()
     .AllowAnyMethod())
);

// EF Core — code-first, PostgreSQL, no migrations
builder.Services.AddDbContext<AppDbContext>(o => o.UseNpgsql(builder.Configuration.GetConnectionString("Postgres")));

// HTTP client for Python agent trigger
builder.Services.AddHttpClient("python-agent", c =>
{
    c.BaseAddress = new Uri(builder.Configuration["PythonAgent:BaseUrl"] ?? "http://localhost:5001/");
    c.Timeout = TimeSpan.FromSeconds(10);
});

// Services
builder.Services.AddScoped<IWatchlistService,        WatchlistService>();
builder.Services.AddScoped<INewsIngestionService,    NewsIngestionService>();
builder.Services.AddScoped<ISignalService,           SignalService>();
builder.Services.AddScoped<IBacktestTriggerService,  BacktestTriggerService>();

// Daily scheduled ingest + backtest recompute (run after ingest so fresh signals/prices are included)
builder.Services.AddHostedService<DailyIngestJob>();
builder.Services.AddHostedService<DailyBacktestJob>();

var app = builder.Build();

// EnsureCreated — creates all tables from EF model on first run (no migrations)
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    await db.Database.EnsureCreatedAsync();
}

app.UseCors();
app.UseSwagger();
app.UseSwaggerUI();
app.UseAuthorization();
app.MapControllers();

app.Run();
