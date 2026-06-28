using Microsoft.EntityFrameworkCore;
using NewsMarketAgent.Api.Data;
using NewsMarketAgent.Api.Models;

namespace NewsMarketAgent.Api.Services;

public interface IWatchlistService
{
    Task<List<WatchlistItem>> GetAllAsync();
    Task AddAsync(AddWatchlistItemDto dto);
    Task RemoveAsync(string ticker);
}

public class WatchlistService(AppDbContext db) : IWatchlistService
{
    public Task<List<WatchlistItem>> GetAllAsync() => db.Watchlist.OrderBy(w => w.Ticker).ToListAsync();

    public async Task AddAsync(AddWatchlistItemDto dto)
    {
        if (!await db.Watchlist.AnyAsync(w => w.Ticker == dto.Ticker))
        {
            db.Watchlist.Add(new WatchlistItem
            {
                Ticker  = dto.Ticker,
                Name    = dto.Name,
                AddedAt = DateTime.UtcNow,
            });
            await db.SaveChangesAsync();
        }
    }

    public async Task RemoveAsync(string ticker)
    {
        var item = await db.Watchlist.FindAsync(ticker);
        if (item is not null)
        {
            db.Watchlist.Remove(item);
            await db.SaveChangesAsync();
        }
    }
}
