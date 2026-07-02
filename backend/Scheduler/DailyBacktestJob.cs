using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Scheduler;

public class DailyBacktestJob(IServiceProvider services, IConfiguration config, ILogger<DailyBacktestJob> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            var now     = DateTime.Now;
            var trigger = TimeOnly.Parse(config["Scheduler:DailyBacktestTime"] ?? "08:00");
            var next    = now.Date.Add(trigger.ToTimeSpan());
            if (next <= now) next = next.AddDays(1);

            while (next.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday)
                next = next.AddDays(1);

            log.LogInformation("Next scheduled backtest recompute: {Next}", next);
            await Task.Delay(next - now, stoppingToken);

            try
            {
                using var scope    = services.CreateScope();
                var backtest        = scope.ServiceProvider.GetRequiredService<IBacktestTriggerService>();
                await backtest.RecomputeAsync();
            }
            catch (Exception ex)
            {
                log.LogError(ex, "Scheduled backtest recompute failed");
            }
        }
    }
}
