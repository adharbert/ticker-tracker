using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Scheduler;

public class DailyIngestJob(IServiceProvider services, IConfiguration config, ILogger<DailyIngestJob> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            var now     = DateTime.Now;
            var trigger = TimeOnly.Parse(config["Scheduler:DailyIngestTime"] ?? "07:00");
            var next    = now.Date.Add(trigger.ToTimeSpan());
            if (next <= now) next = next.AddDays(1);

            while (next.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday)
                next = next.AddDays(1);

            log.LogInformation("Next scheduled ingest: {Next}", next);
            await Task.Delay(next - now, stoppingToken);

            try
            {
                using var scope  = services.CreateScope();
                var ingest       = scope.ServiceProvider.GetRequiredService<INewsIngestionService>();
                await ingest.IngestLatestAsync();
            }
            catch (Exception ex)
            {
                log.LogError(ex, "Scheduled ingest failed");
            }
        }
    }
}
