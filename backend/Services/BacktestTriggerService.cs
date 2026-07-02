namespace NewsMarketAgent.Api.Services;

public interface IBacktestTriggerService
{
    Task<string> RecomputeAsync();
}

public class BacktestTriggerService(IHttpClientFactory http, ILogger<BacktestTriggerService> log) : IBacktestTriggerService
{
    public async Task<string> RecomputeAsync()
    {
        var client = http.CreateClient("python-agent");
        try
        {
            var resp = await client.PostAsync("/backtest/trigger", null);
            if (resp.IsSuccessStatusCode)
            {
                log.LogInformation("Backtest recompute triggered on Python agent");
                return "triggered";
            }
            log.LogWarning("Python agent returned {Status}", resp.StatusCode);
            return "python_agent_error";
        }
        catch (HttpRequestException ex)
        {
            log.LogError(ex, "Could not reach Python agent at {Base}", client.BaseAddress);
            return "python_agent_unreachable";
        }
    }
}
